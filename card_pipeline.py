"""
Data Expo Avatar Card - generation & composition pipeline (v7).

Changes vs v6:
- All "game design" logic (the answer -> archetype tables, the rarity
  roll, the avatar prompt builder) moved out to game_rules.py, which is
  pure and dependency-free - no AI calls, no file I/O, fully unit
  testable on its own. This file keeps everything that touches the
  outside world: AI calls (name/skill text/avatar), file I/O, and PIL
  card composition. See game_rules.py's module docstring for the full
  rationale.
- Fixed a real logical inconsistency: the top-right badge used to show a
  made-up "XP" number (0-1000, rescaled from the HP/resilience question)
  sitting right next to the Level badge - which strongly implies XP
  feeds Level, like in an actual RPG. It doesn't; they come from two
  completely unrelated questions. The badge now honestly shows the raw
  HP value (90-170, matching the original brief) labeled "HP", removing
  both the fake rescaling and the misleading implied link to Level.
- The avatar prompt (now in game_rules.build_avatar_prompt) asks for
  Pokemon-trading-card-style art: a bold character filling most of the
  frame with a real themed environment behind it, instead of a small
  character floating in empty background margin - see game_rules.py's
  TYPE_ENVIRONMENTS and AVATAR_STYLE_SUFFIX for details.

Run this file directly to test the full pipeline against example/mock data
without the Streamlit UI:

    python card_pipeline.py

TEST_USE_AI = False (default) skips all API calls entirely (name/skill text
use rule-based fallbacks, avatar uses a solid placeholder square) so you can
check the layout for free. Flip it to True once MAI_ENDPOINT / MAI_API_KEY
(for the avatar) and OPENAI_API_KEY (for name/skill text, optional) are set.
"""

from __future__ import annotations

import base64
import json
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from PIL import Image, ImageDraw, ImageFont

from game_rules import (
    ANIMAL_PREF_OPTIONS,
    COLOR_PREF_OPTIONS,
    RARITY_TIER_INDEX,
    STYLE_VIBE_OPTIONS,
    GameResult,
    QuestionnaireAnswers,
    build_avatar_prompt,
    resolve_game,
)

# --------------------------------------------------------------------------
# Paths & setup
# --------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / "environment_variables.env"
load_dotenv(dotenv_path=ENV_PATH)

# Name / skill-text generation (optional - falls back to rule-based if unset)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client: Optional[OpenAI] = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Avatar generation - Microsoft MAI-Image-2.5 via Azure AI Foundry.
MAI_ENDPOINT = os.getenv("MAI_ENDPOINT")
MAI_API_KEY = os.getenv("MAI_API_KEY")
MAI_DEPLOYMENT_NAME = os.getenv("MAI_DEPLOYMENT_NAME", "mai-image-2.5")

INPUT_FOLDER = BASE_DIR / "input_images"
OUTPUT_FOLDER = BASE_DIR / "output_images"
CARD_FOLDER = BASE_DIR / "cards"
ASSETS_FOLDER = BASE_DIR / "assets"
FONTS_FOLDER = ASSETS_FOLDER / "fonts"
COUNTER_FILE = BASE_DIR / "card_counter.txt"

for p in (INPUT_FOLDER, OUTPUT_FOLDER, CARD_FOLDER, ASSETS_FOLDER, FONTS_FOLDER):
    p.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Shared layout constants
# --------------------------------------------------------------------------

DPI = 300
MM_TO_INCH = 0.0393701
CARD_SIZE_MM = (105, 148)  # A6
CARD_W = int(CARD_SIZE_MM[0] * MM_TO_INCH * DPI)
CARD_H = int(CARD_SIZE_MM[1] * MM_TO_INCH * DPI)

MARGIN = int(CARD_W * 0.055)
BORDER_RADIUS = 24
BORDER_WIDTH = 5

FRONT_DESIGN_VERSION = "v4"

BRAND_RED = "#FF3D47"
G20 = "#E6DEDA"
G30 = "#CCC1BC"
G50 = "#98847A"

AVATAR_SLOT_SIZE = (1000, 1000)
AVATAR_GEN_SIZE = 1024
MAX_SKILL_TEXT_CHARS = 200


@dataclass
class CardData:
    card_number: str
    pokemon_name: str
    level_name: str
    hp_flavor: str
    hp_value: int
    capability: str
    domain_tag: str
    skill_name: str
    skill_text: str
    signature_move: str
    progress_stage: int
    progress_label: str
    rarity: str
    rarity_color: str
    avatar_path: Path
    card_back_path: Optional[Path] = None
    card_front_path: Optional[Path] = None


_NAME_SUFFIXES = ["ion", "yra", "orix", "ara", "eon", "ux", "andra", "ivo", "oz", "ex"]
_BLOCKED_SUBSTRINGS = {
    "damn", "hell", "sex", "kill", "nazi", "hitler", "fuck", "shit", "cunt", "rape",
}


def _is_name_safe(name: str) -> bool:
    lowered = name.lower()
    return bool(name) and name.isascii() and len(name) <= 20 and not any(bad in lowered for bad in _BLOCKED_SUBSTRINGS)


def generate_name_rule_based(first_name: str) -> str:
    stem = re.sub(r"[^A-Za-z]", "", first_name).rstrip("aeiouAEIOU") or re.sub(r"[^A-Za-z]", "", first_name) or "Data"
    suffix = random.choice(_NAME_SUFFIXES)
    return f"{stem[0].upper()}{stem[1:]}{suffix}"


def generate_name(first_name: str, use_ai: bool = True) -> str:
    candidate = None
    if use_ai and openai_client is not None:
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You invent short, fun, Pokemon-style fantasy names based on a person's "
                            "first name, for a professional conference event. Rules: "
                            "1) Output ONLY the name, nothing else. "
                            "2) Max 14 characters. "
                            "3) Must sound playful and positive, never offensive, never a real slur or "
                            "profanity, never a real-world weapon/violence reference. "
                            "4) It should clearly sound derived from the given first name."
                        ),
                    },
                    {"role": "user", "content": f"First name: {first_name}"},
                ],
                max_tokens=10,
                temperature=0.8,
            )
            candidate = (response.choices[0].message.content or "").strip().split()[0]
        except (OpenAIError, Exception) as e:
            print(f"Name generation via LLM failed, falling back to rule-based: {e}")
            candidate = None

    if not candidate or not _is_name_safe(candidate):
        candidate = generate_name_rule_based(first_name)
    if not _is_name_safe(candidate):
        candidate = f"{re.sub(r'[^A-Za-z]', '', first_name) or 'Data'}ion"
    return candidate


def generate_avatar(
    card_number: str,
    result: GameResult,
    color_pref: str = "Classic Red",
    animal_pref: str = "Owl",
    style_vibe: str = "Cute & sparkly",
) -> Path:
    """
    Generate a fully text-to-image avatar via Microsoft's MAI-Image-2.5 model
    on Azure AI Foundry. The actual prompt content lives in
    game_rules.build_avatar_prompt(); this just calls the API and
    post-processes the result.

    API reference: https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-mai-image
    """
    if not MAI_ENDPOINT or not MAI_API_KEY:
        raise RuntimeError(
            "MAI_ENDPOINT / MAI_API_KEY not configured in environment_variables.env - "
            "cannot generate avatar image. See README for how to get these from the "
            "Foundry portal."
        )

    prompt = build_avatar_prompt(result, color_pref, animal_pref, style_vibe)
    url = f"{MAI_ENDPOINT.rstrip('/')}/mai/v1/images/generations"
    payload = {
        "model": MAI_DEPLOYMENT_NAME,
        "prompt": prompt,
        "width": AVATAR_GEN_SIZE,
        "height": AVATAR_GEN_SIZE,
    }

    response = requests.post(
        url,
        headers={"Content-Type": "application/json", "api-key": MAI_API_KEY},
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    api_result = response.json()

    image_entries = [entry for entry in api_result.get("data", []) if "b64_json" in entry]
    if not image_entries:
        raise RuntimeError(f"Unexpected response format from MAI-Image-2.5: {api_result}")

    image_bytes = base64.b64decode(image_entries[0]["b64_json"])
    raw_path = OUTPUT_FOLDER / f"{card_number}_raw.png"
    raw_path.write_bytes(image_bytes)

    fitted_path = OUTPUT_FOLDER / f"{card_number}_avatar.png"
    _fit_to_slot(raw_path, fitted_path, AVATAR_SLOT_SIZE)
    return fitted_path


def _fit_to_slot(src_path: Path, dst_path: Path, slot_size: tuple[int, int]) -> None:
    img = Image.open(src_path).convert("RGB")
    target_ratio = slot_size[0] / slot_size[1]
    img_ratio = img.width / img.height

    if img_ratio > target_ratio:
        new_width = int(img.height * target_ratio)
        left = (img.width - new_width) // 2
        img = img.crop((left, 0, left + new_width, img.height))
    else:
        new_height = int(img.width / target_ratio)
        top = (img.height - new_height) // 2
        img = img.crop((0, top, img.width, top + new_height))

    img = img.resize(slot_size, Image.Resampling.LANCZOS)
    img.save(dst_path)


def generate_skill_text_rule_based(attack_text: str) -> str:
    return attack_text[:MAX_SKILL_TEXT_CHARS]


def generate_skill_text(ability: str, attack_text: str, use_ai: bool = True) -> str:
    if use_ai and openai_client is not None:
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You write short, funny, office-safe flavor text for a trading-card style "
                            "'signature skill' section at a corporate data conference. "
                            f"Hard limit: {MAX_SKILL_TEXT_CHARS} characters, plain text, no markdown, "
                            "no profanity, no real people's names, no company names other than generic "
                            "workplace terms. Playful data/office humor tone, 2-3 short sentences."
                        ),
                    },
                    {"role": "user", "content": f"Ability: {ability}\nHumor reference line: {attack_text}"},
                ],
                max_tokens=120,
                temperature=0.9,
            )
            text = (response.choices[0].message.content or "").strip()
            if text and len(text) <= MAX_SKILL_TEXT_CHARS + 20:
                return text[:MAX_SKILL_TEXT_CHARS]
        except (OpenAIError, Exception) as e:
            print(f"Skill text generation via LLM failed, falling back to rule-based: {e}")

    return generate_skill_text_rule_based(attack_text)


def next_card_number() -> str:
    count = 1
    if COUNTER_FILE.exists():
        try:
            count = int(COUNTER_FILE.read_text().strip()) + 1
        except ValueError:
            count = 1
    COUNTER_FILE.write_text(str(count))
    return f"DA-{count:03d}"


def build_card_data(answers: QuestionnaireAnswers, use_ai: bool = True, progress_callback=None) -> CardData:
    """
    progress_callback, if given, is called with a short status string before
    each step - e.g. `lambda msg: st.write(msg)` in Streamlit - purely to
    drive a nicer loading experience. Optional; pipeline works fine without it.
    """
    def _report(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    _report("🔢 Crunching your answers...")
    card_number = next_card_number()
    result = resolve_game(answers)
    _report(f"🎲 You rolled **{result.rarity}**!")

    _report("🪄 Naming your data alter-ego...")
    pokemon_name = generate_name(answers.first_name, use_ai=use_ai)
    _report(f"Meet **{pokemon_name}**!")

    _report("✍️ Writing your signature skill...")
    skill_text = generate_skill_text(result.skill_name, result.attack_text_line, use_ai=use_ai)

    if use_ai:
        _report("🎨 Painting your data creature (this is the slow part, hang tight)...")
        avatar_path = generate_avatar(
            card_number, result,
            color_pref=answers.color_pref, animal_pref=answers.animal_pref, style_vibe=answers.style_vibe,
        )
    else:
        avatar_path = OUTPUT_FOLDER / f"{card_number}_avatar_placeholder.png"
        Image.new("RGB", AVATAR_SLOT_SIZE, BRAND_RED).save(avatar_path)

    _report("🖼️ Assembling your card...")

    return CardData(
        card_number=card_number,
        pokemon_name=pokemon_name,
        level_name=result.level_name,
        hp_flavor=result.hp_flavor,
        hp_value=result.hp_value,
        capability=result.capability,
        domain_tag=result.domain_tag,
        skill_name=result.skill_name,
        skill_text=skill_text,
        signature_move=result.signature_move,
        progress_stage=result.progress_stage,
        progress_label=result.progress_label,
        rarity=result.rarity,
        rarity_color=BRAND_RED,
        avatar_path=avatar_path,
    )


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    candidates = [FONTS_FOLDER / name, FONTS_FOLDER / "brand-regular.ttf"]
    for path in candidates:
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            continue
    return ImageFont.load_default()


def _font_bold(size: int) -> ImageFont.FreeTypeFont:
    return _load_font("brand-bold.ttf", size)


def _font_medium(size: int) -> ImageFont.FreeTypeFont:
    return _load_font("brand-medium.ttf", size)


def _font_regular(size: int) -> ImageFont.FreeTypeFont:
    return _load_font("brand-regular.ttf", size)


def _draw_outer_frame(draw: ImageDraw.ImageDraw, color: str) -> None:
    draw.rounded_rectangle(
        [MARGIN // 2, MARGIN // 2, CARD_W - MARGIN // 2, CARD_H - MARGIN // 2],
        radius=BORDER_RADIUS, outline=color, width=BORDER_WIDTH,
    )


def _draw_diamond(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill=None, outline=None, width: int = 2) -> None:
    points = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    if fill is not None:
        draw.polygon(points, fill=fill)
    else:
        draw.polygon(points, outline=outline, width=width)


def _draw_rarity_stamp(draw, right_x, y, rarity, filled_color, empty_color, text_color, font) -> None:
    tier = RARITY_TIER_INDEX[rarity]
    diamond_r = 11
    gap = 10
    diamonds_w = 5 * (diamond_r * 2) + 4 * gap

    label = rarity.upper()
    label_w = draw.textlength(label, font=font)

    diamonds_x = right_x - diamonds_w
    label_x = diamonds_x - 16 - label_w

    draw.text((label_x, y), label, font=font, fill=text_color, anchor="lm")

    cx = diamonds_x + diamond_r
    cy = y
    for i in range(5):
        if i < tier:
            _draw_diamond(draw, cx, cy, diamond_r, fill=filled_color)
        else:
            _draw_diamond(draw, cx, cy, diamond_r, outline=empty_color, width=3)
        cx += diamond_r * 2 + gap


def _draw_dotted_line(draw, x1, y, x2, color, width: int = 4, dot_r: int = 7) -> None:
    draw.line([x1 + dot_r, y, x2 - dot_r, y], fill=color, width=width)
    draw.ellipse([x1, y - dot_r, x1 + dot_r * 2, y + dot_r], fill=color)
    draw.ellipse([x2 - dot_r * 2, y - dot_r, x2, y + dot_r], fill=color)


def compose_card_back(card: CardData, output_path: Optional[Path] = None) -> Path:
    output_path = output_path or (CARD_FOLDER / f"{card.card_number}_back.png")

    canvas = Image.new("RGB", (CARD_W, CARD_H), G20)
    draw = ImageDraw.Draw(canvas)
    _draw_outer_frame(draw, card.rarity_color)

    x = MARGIN + BORDER_WIDTH + 10
    right_x = CARD_W - MARGIN - BORDER_WIDTH - 10
    y = MARGIN + BORDER_WIDTH + 20

    # --- Level badge (top-left) & HP badge (top-right) ---
    # Shows the raw HP value (90-170), not a rescaled pseudo-XP number - see
    # the module docstring for why that matters.
    badge_font = _font_medium(34)
    badge_h = 66
    draw.rounded_rectangle([x, y, x + 300, y + badge_h], radius=badge_h // 2, fill=G30)
    draw.text((x + 26, y + badge_h // 2), card.level_name.upper(), font=badge_font, fill="black", anchor="lm")

    hp_text = f"{card.hp_value} HP"
    hp_w = 190
    draw.rounded_rectangle([right_x - hp_w, y, right_x, y + badge_h], radius=badge_h // 2, fill=G30)
    draw.text((right_x - hp_w / 2, y + badge_h // 2), hp_text, font=badge_font, fill="black", anchor="mm")

    _draw_rarity_stamp(
        draw, right_x, y + badge_h + 30, card.rarity,
        filled_color=card.rarity_color, empty_color="#DEDAD6", text_color="black",
        font=_font_medium(26),
    )

    y += badge_h + 55

    title_font = _font_bold(70)
    draw.text((x, y), card.pokemon_name, font=title_font, fill="black")
    y += 90

    cap_font = _font_medium(36)
    domain_font = _font_regular(25)
    draw.ellipse([x, y + 5, x + 28, y + 33], fill=card.rarity_color)
    draw.text((x + 42, y), card.capability, font=cap_font, fill="black")
    cap_w = draw.textlength(card.capability, font=cap_font)
    draw.text((x + 42 + cap_w + 16, y + 7), card.domain_tag.upper(), font=domain_font, fill=G50)
    y += 56

    # --- Avatar - spans nearly the full content width between the margins,
    # as a center-cropped landscape rectangle (numerically tested against
    # the worst-case max-length skill text so it never overlaps the
    # signature move / progress section below it) ---
    avatar_w = int((right_x - x) * 0.94)
    avatar_h = 660
    avatar_x = (CARD_W - avatar_w) // 2
    cropped_avatar_path = OUTPUT_FOLDER / f"{card.card_number}_avatar_card_crop.png"
    _fit_to_slot(card.avatar_path, cropped_avatar_path, (avatar_w, avatar_h))
    avatar = Image.open(cropped_avatar_path).convert("RGB")
    canvas.paste(avatar, (avatar_x, y))
    draw.rectangle([avatar_x, y, avatar_x + avatar_w, y + avatar_h], outline=card.rarity_color, width=4)
    y += avatar_h + 26

    label_font = _font_bold(30)
    skill_name_font = _font_bold(50)
    body_font = _font_regular(32)

    draw.rectangle([x, y, x + 12, y + 38], fill=card.rarity_color)
    draw.text((x + 26, y), "SIGNATURE SKILL", font=label_font, fill=G50)
    y += 46
    draw.text((x, y), card.skill_name, font=skill_name_font, fill="black")
    y += 60
    _draw_dotted_line(draw, x, y, right_x, BRAND_RED)
    y += 18

    y = _draw_wrapped_text(draw, card.skill_text, (x, y), body_font, right_x - x, max_lines=3)

    y += 18
    move_label_font = _font_bold(26)
    move_value_font = _font_medium(28)
    draw.text((x, y), "SIGNATURE MOVE", font=move_label_font, fill=G50)
    label_w = draw.textlength("SIGNATURE MOVE", font=move_label_font)
    draw.text((x + label_w + 14, y + 1), card.signature_move, font=move_value_font, fill="black")
    y += 40

    progress_y = CARD_H - MARGIN - 190
    draw.text((x, progress_y), "PROGRESS", font=label_font, fill=G50)
    dot_y = progress_y + 46
    dot_x = x
    dot_d = 38
    for i in range(5):
        fill = card.rarity_color if i < card.progress_stage else "#DEDAD6"
        draw.ellipse([dot_x, dot_y, dot_x + dot_d, dot_y + dot_d], fill=fill)
        dot_x += dot_d + 14

    pill_w = 220
    draw.rounded_rectangle([right_x - pill_w, dot_y - 8, right_x, dot_y + dot_d + 8], radius=dot_d, fill=card.rarity_color)
    draw.text((right_x - pill_w / 2, dot_y + dot_d / 2), card.progress_label, font=_font_medium(28), fill="black", anchor="mm")

    number_y = CARD_H - MARGIN - 58
    _draw_dotted_line(draw, x, number_y - 18, right_x, BRAND_RED, width=3, dot_r=6)
    draw.text((x, number_y), "B°", font=_font_bold(34), fill=BRAND_RED)
    card_number_w = draw.textlength(card.card_number, font=body_font)
    draw.text((right_x - card_number_w, number_y + 4), card.card_number, font=body_font, fill="black")

    canvas.save(output_path, dpi=(DPI, DPI))
    card.card_back_path = output_path
    return output_path


def _draw_wrapped_text(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], font, max_width: int, max_lines: int = 6) -> int:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    x, y = xy
    line_height = getattr(font, "size", 24) + 12
    for line in lines[:max_lines]:
        draw.text((x, y), line, font=font, fill="black")
        y += line_height
    return y


def compose_card_front(rarity: str, output_path: Optional[Path] = None, force: bool = False) -> Path:
    """
    Static card front (the branded BearingPoint side), rendered once per
    rarity tier and cached under assets/. Uses a real logo image if you
    drop one at assets/bp_wordmark_black.png, otherwise falls back to a
    bold text wordmark - either way the design stays black-on-red per
    brand guidelines (no white-on-red).

    IMPORTANT while iterating: this caches its output per rarity (and per
    FRONT_DESIGN_VERSION). Bump FRONT_DESIGN_VERSION whenever you change
    this function so old cached files stop being picked up automatically -
    or pass force=True to regenerate on demand without bumping it.
    """
    cached = ASSETS_FOLDER / f"front_{rarity.lower()}_{FRONT_DESIGN_VERSION}.png"
    if cached.exists() and output_path is None and not force:
        return cached

    output_path = output_path or cached

    canvas = Image.new("RGB", (CARD_W, CARD_H), BRAND_RED)
    draw = ImageDraw.Draw(canvas)
    _draw_outer_frame(draw, "black")

    brand_font = _font_bold(96)
    tagline_font = _font_medium(38)
    sub_font = _font_regular(30)

    logo_path = ASSETS_FOLDER / "bp_wordmark_black.png"
    if logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        target_w = int(CARD_W * 0.6)
        scale = target_w / logo.width
        logo = logo.resize((target_w, int(logo.height * scale)), Image.Resampling.LANCZOS)
        logo_x = (CARD_W - logo.width) // 2
        logo_y = int(CARD_H * 0.22) - logo.height // 2
        canvas.paste(logo, (logo_x, logo_y), logo)
    else:
        draw.text((CARD_W // 2, int(CARD_H * 0.22)), "BearingPoint", font=brand_font, fill="black", anchor="mm")

    draw.line([MARGIN + 60, int(CARD_H * 0.29), CARD_W - MARGIN - 60, int(CARD_H * 0.29)], fill="black", width=3)

    arrow_path = ASSETS_FOLDER / "data_arrow.png"
    if arrow_path.exists():
        arrow = Image.open(arrow_path).convert("RGBA")
        target_w = int(CARD_W * 0.62)
        scale = target_w / arrow.width
        arrow = arrow.resize((target_w, int(arrow.height * scale)), Image.Resampling.LANCZOS)
        arrow_x = (CARD_W - arrow.width) // 2
        arrow_y = int(CARD_H * 0.5) - arrow.height // 2
        canvas.paste(arrow, (arrow_x, arrow_y), arrow)

    draw.text((CARD_W // 2, int(CARD_H * 0.83)), "Master Data. Train AI.", font=tagline_font, fill="black", anchor="mm")
    draw.text((CARD_W // 2, int(CARD_H * 0.865)), "Create Impact.", font=tagline_font, fill="black", anchor="mm")
    draw.text((CARD_W // 2, int(CARD_H * 0.91)), "Data Expo Series", font=sub_font, fill="black", anchor="mm")

    _draw_rarity_stamp(
        draw, CARD_W - MARGIN - BORDER_WIDTH - 20, int(CARD_H * 0.955), rarity,
        filled_color="black", empty_color="#B02530", text_color="black",
        font=_font_medium(26),
    )

    canvas.save(output_path, dpi=(DPI, DPI))
    return output_path


if __name__ == "__main__":
    TEST_USE_AI = False  # flip to True once MAI_ENDPOINT/MAI_API_KEY (and optionally OPENAI_API_KEY) are set

    example_answers = QuestionnaireAnswers(
        first_name="Jasper",
        evolution=3,
        type_=5,
        hp=4,
        ability=5,
        attack_text=5,
        attack2=4,
        color_pref="Royal Purple",
        animal_pref="Owl",
        style_vibe="Sleek & futuristic",
    )

    card = build_card_data(example_answers, use_ai=TEST_USE_AI)
    print(json.dumps({
        "card_number": card.card_number,
        "pokemon_name": card.pokemon_name,
        "level_name": card.level_name,
        "hp_value": card.hp_value,
        "hp_flavor": card.hp_flavor,
        "capability": card.capability,
        "domain_tag": card.domain_tag,
        "signature_move": card.signature_move,
        "skill_name": card.skill_name,
        "skill_text": card.skill_text,
        "progress_stage": card.progress_stage,
        "progress_label": card.progress_label,
        "rarity": card.rarity,
    }, indent=2))

    back_path = compose_card_back(card)
    front_path = compose_card_front(card.rarity)
    print(f"Card back saved to: {back_path}")
    print(f"Card front saved to: {front_path}")
