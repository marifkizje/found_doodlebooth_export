"""
Data Expo Avatar Card - generation & composition pipeline (v2).

Changes vs. v1:
- No more photos. The avatar is now generated purely from text (via
  Microsoft's MAI-Image-2.5 model on Azure AI Foundry), based on the
  person's questionnaire answers - no face/privacy data is captured or
  sent anywhere, which sidesteps GDPR/consent questions around photos of
  attendees entirely.
- Fixed the "letters are tiny" issue: the previous version fell back to
  PIL's `ImageFont.load_default()` whenever a brand font file was missing,
  and that font silently ignores the requested size (always renders ~10px)
  - so it looked tiny even though the code asked for size 64. This version
  bundles real, legible open-source fonts (Poppins, similar in spirit to
  many corporate sans-serif brand fonts) as the fallback under
  assets/fonts/, so text is always properly sized even before final brand
  fonts are dropped in. Font sizes were also increased significantly.
- Fixed front/back registration for double-sided printing: both sides now
  share one single set of layout constants (MARGIN, BORDER_RADIUS,
  BORDER_WIDTH, CARD_W, CARD_H) instead of each having their own slightly
  different margin, so the outer border/frame lines up between front and
  back. See print_utils.py for a printer alignment-test helper you should
  run once on your actual printer/paper-flip method before the event -
  code alone can guarantee the two images are pixel-identical in size and
  border position, but the physical flip (which edge you flip the card on)
  is a hardware/workflow detail that needs a quick real-world test.

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

# --------------------------------------------------------------------------
# Paths & setup
# --------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = "/Users/kizje.marif/Downloads/found_doodlebooth_export/environment_variables.env" #BASE_DIR / "environment_variables.env"
load_dotenv(dotenv_path=ENV_PATH)


# Name / skill-text generation (optional - falls back to rule-based if unset)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client: Optional[OpenAI] = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Avatar generation - Microsoft MAI-Image-2.5 via Azure AI Foundry.
# MAI_ENDPOINT looks like: https://<resource-name>.services.ai.azure.com
# MAI_DEPLOYMENT_NAME is the deployment name you gave the model in Foundry
# (defaults to "mai-image-2.5" - check the Foundry portal under Deployments
# if that's not what you named it).
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
# Shared layout constants - used by BOTH compose_card_front and
# compose_card_back, so the outer frame lines up between the two sides when
# printed double-sided. Don't define margin/border separately per function.
# --------------------------------------------------------------------------

DPI = 300
MM_TO_INCH = 0.0393701
CARD_SIZE_MM = (105, 148)  # A6
CARD_W = int(CARD_SIZE_MM[0] * MM_TO_INCH * DPI)
CARD_H = int(CARD_SIZE_MM[1] * MM_TO_INCH * DPI)

MARGIN = int(CARD_W * 0.055)
BORDER_RADIUS = 28
BORDER_WIDTH = 10

# Bump this whenever compose_card_front's design changes (colors, layout,
# fonts, etc.). It's baked into the cache filename below, so old cached
# fronts automatically stop being picked up instead of silently going
# stale - no more "front looks like the old design" confusion after an
# update, without needing to remember to manually delete assets/front_*.png.
FRONT_DESIGN_VERSION = "v3"

# --------------------------------------------------------------------------
# Rule-based mappings (questionnaire answer 1-5 -> named result)
# --------------------------------------------------------------------------

EVOLUTION_STAGES = {
    1: "Data Sprout",
    2: "Data Scout",
    3: "Data Voyager",
    4: "Data Master",
    5: "Data Legend",
}

POKEMON_TYPES = {
    1: "Data Noob",
    2: "Pipeline Fox",
    3: "Data Guardian",
    4: "Insight Owl",
    5: "Pattern Seeker",
    6: "AI Sprinter",
}

# Small domain tag shown alongside the type name on the card, so it lands
# clearly as "which facet of data work are you" rather than a made-up word.
TYPE_DOMAIN_TAGS = {
    "Data Noob": "Just Getting Started",
    "Pipeline Fox": "Data Engineering",
    "Data Guardian": "Data Management",
    "Insight Owl": "Analytics & BI",
    "Pattern Seeker": "Data Science",
    "AI Sprinter": "AI & ML",
}

HP_TIERS = {
    1: ("Calm Builder", 90),
    2: ("Steady Planner", 110),
    3: ("Data Beaver", 130),
    4: ("Chaos Tamer", 150),
    5: ("Deadline Dragon", 170),
}

ABILITIES = {
    1: "Sharp Eye",
    2: "Bright Spark",
    3: "Helping Hand",
    4: "Problem Catcher",
    5: "Data Whisperer",
}

ATTACK_1 = {
    1: "Lightning Start",
    2: "Smart Shortcut",
    3: "Data Quest",
    4: "Clarity Beam",
    5: "Signal Wave",
}

ATTACK_TEXT = {
    1: "Discover one hidden insight in the data. Nobody knew it existed, but you found it in five minutes.",
    2: "Bring order to a messy dataset. Even the column names thank you personally.",
    3: "This attack deals 10 extra damage for every KPI that is actually being used thanks to you.",
    4: "Discover an opportunity before anyone else spots it.",
    5: 'If a stakeholder says, "That\'s exactly what I meant," double the damage of this attack.',
}

ATTACK_2 = {
    1: "Brainstorm Cyclone",
    2: "Workshop Whirlwind",
    3: "Alignment Cannon",
    4: "Dataflow Inferno",
    5: "Hero Mode",
}

RARITY_WEIGHTS = {
    "Common": 50,
    "Rare": 30,
    "Epic": 15,
    "Legendary": 4,
    "Mythic": 1,
}

# Single fixed brand accent, used for everything on every card regardless
# of rarity - placeholder hex, swap in the exact brand red before print.
# Rarity is communicated separately via a small diamond indicator (see
# RARITY_TIER_INDEX + _draw_rarity_stamp), not via a different card color.
BRAND_RED = "#C8102E"

RARITY_TIER_INDEX = {
    "Common": 1,
    "Rare": 2,
    "Epic": 3,
    "Legendary": 4,
    "Mythic": 5,
}

# Visual direction per Pokemon-type, fed into the avatar's text prompt so
# each type has a recognizably different look even without a photo.
TYPE_VISUAL_HINTS = {
    "Data Noob": "a bewildered creature clutching a giant coffee mug, surrounded by an intimidating stack of unopened spreadsheets",
    "Pipeline Fox": "a calm, capable creature quietly patching a leaking pipe or conveyor belt before anyone even notices",
    "Data Guardian": "a meticulous creature carefully filing glowing folders and labels into neat, orderly archive boxes",
    "Insight Owl": "a sharp-eyed creature tracing a glowing trend line rising up out of a messy cloud of scattered dots",
    "Pattern Seeker": "an excited creature surrounded by floating puzzle-piece-shaped fragments it's assembling into a hidden formula",
    "AI Sprinter": "a creature reaching eagerly toward a glowing holographic 'NEW' button, leaving a trail of light behind it",
}

RARITY_VISUAL_HINTS = {
    "Common": "a simple, clean design",
    "Rare": "a subtle soft glowing aura",
    "Epic": "ornate glowing patterns and small floating data-sparkles around it",
    "Legendary": "a radiant magical aura with dramatic rim lighting",
    "Mythic": "an extraordinary, almost mythical presence with intricate glowing linework and dramatic atmosphere",
}

# Fun, purely cosmetic questionnaire options - only used to flavor the
# avatar image prompt (see _build_avatar_prompt). Keep option lists short
# and playful; nothing here touches Level/XP/Capability/etc.
COLOR_PREF_OPTIONS = ["Electric Blue", "Sunset Orange", "Neon Green", "Royal Purple", "Classic Red"]
ANIMAL_PREF_OPTIONS = ["Owl", "Fox", "Dragon", "Cat", "Robot Bunny"]
STYLE_VIBE_OPTIONS = ["Cute & sparkly", "Sleek & futuristic", "Bold & fierce", "Calm & zen", "Retro & funky"]


def _progress_label(stage: int) -> str:
    if stage <= 2:
        return "starter"
    if stage == 3:
        return "skilled"
    return "expert"


# --------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------

@dataclass
class QuestionnaireAnswers:
    first_name: str
    evolution: int   # 1-5
    type_: int       # 1-5
    hp: int          # 1-5
    ability: int     # 1-5
    attack1: int     # 1-5
    attack_text: int # 1-5
    attack2: int     # 1-5
    # Fun personalization - purely cosmetic, only used to flavor the avatar
    # image prompt. Doesn't affect Level/XP/Capability/etc. at all.
    color_pref: str = "Classic Red"
    animal_pref: str = "Owl"
    style_vibe: str = "Cute & sparkly"

    def __post_init__(self):
        for name in ("evolution", "hp", "ability", "attack1", "attack_text", "attack2"):
            value = getattr(self, name)
            if value not in (1, 2, 3, 4, 5):
                raise ValueError(f"{name} must be 1-5, got {value}")
        if self.type_ not in (1, 2, 3, 4, 5, 6):
            raise ValueError(f"type_ must be 1-6, got {self.type_}")


@dataclass
class CardData:
    card_number: str
    pokemon_name: str
    level_name: str
    xp: int
    hp_flavor: str
    hp_value: int
    capability: str
    domain_tag: str
    skill_name: str
    skill_text: str
    progress_stage: int
    progress_label: str
    rarity: str
    rarity_color: str
    avatar_path: Path
    card_back_path: Optional[Path] = None
    card_front_path: Optional[Path] = None


# --------------------------------------------------------------------------
# 1. Name generation (rule-safe) - unchanged from v1
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# 2. Avatar image generation - now text-to-image only, via MAI-Image-2.5
# --------------------------------------------------------------------------

AVATAR_STYLE_SUFFIX = (
    "Bold, professional character-design illustration - think modern brand mascot or game "
    "avatar rather than a generic plush toy. It does not need to look soft, cute, or fluffy - "
    "let it be sleek, tough, elegant, or quirky, whatever the vibe below calls for. Original "
    "design only - NOT a real person, NOT any existing copyrighted character or franchise. "
    "Square composition, character centered with generous background margin, no text, no "
    "logos, no watermarks, professional-event appropriate."
)

# Specific, varied data-themed design details - one is picked at random per
# avatar so the "data" element is an actual visual idea instead of a
# generic glow/circuit-pattern cliché, and so avatars vary even more.
DATA_MOTIF_OPTIONS = [
    "a coat/skin pattern that reads as a subtle scatter plot of dots",
    "a small bar-chart-shaped mohawk or crest on top of its head",
    "sharp glasses or goggles that reflect a faint line graph across the lenses",
    "a tail shaped like a confidently rising trend line",
    "markings arranged in a neat heatmap grid across part of its body",
    "one small pie-chart-shaped accessory - a badge, button, or earring",
    "a collar or scarf woven from tiny glowing binary digits",
    "spots scattered like a data point cloud, denser on one side",
    "a single sharp status-light badge pinned to its chest, like a conference lanyard pin",
    "ears or fins shaped like a little bar chart, each lobe a different height",
    "a belt or strap patterned like a spreadsheet grid",
    "one eye subtly styled like a radar/scatter chart with a faint sweep line",
]


AVATAR_SLOT_SIZE = (1000, 1000)  # px - target size of the photo slot on the card
AVATAR_GEN_SIZE = 1024  # width == height sent to MAI-Image-2.5 (max total pixels 1024*1024)


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _build_avatar_prompt(capability: str, rarity: str, color_pref: str, animal_pref: str, style_vibe: str) -> str:
    """
    Personalization (animal/color/style) leads the prompt and is stated in
    strong, unambiguous terms, since those are the only inputs that should
    make each avatar look genuinely different from the next. One random,
    specific data-design detail replaces the old generic "subtle glow"
    instruction for a more interesting, less cliché result. The
    type/rarity hints stay secondary "personality/flair" notes rather than
    visual instructions, so they nudge the mood without competing with
    animal/color/style for what the model actually renders.
    """
    type_hint = TYPE_VISUAL_HINTS.get(capability, "a friendly data creature")
    rarity_hint = RARITY_VISUAL_HINTS.get(rarity, "a simple, clean design")
    data_motif = random.choice(DATA_MOTIF_OPTIONS)
    article = _article(animal_pref)

    return (
        f"Design an original character avatar clearly and recognizably based on {article} "
        f"{animal_pref.lower()} - keep its signature {animal_pref.lower()} features (silhouette, "
        f"ears/wings/tail, face shape) clearly readable, reimagined as a bold illustrated character. "
        f"Its color palette must be unmistakably {color_pref.lower()} - that color should be the "
        f"dominant hue covering most of its body/fur/scales/skin, not a small accent. "
        f"Give it one specific, fun data-themed design detail: {data_motif}. "
        f"Overall mood and styling: {style_vibe.lower()} - let this genuinely shape its attitude, "
        f"expression, and pose; it should not default to cute or fluffy unless this vibe calls for it. "
        f"Let its pose and expression also carry a hint of this personality trait: {type_hint}. "
        f"Rarity flair to layer on top, without changing the color palette above: {rarity_hint}. "
        f"{AVATAR_STYLE_SUFFIX}"
    )


def generate_avatar(
    card_number: str,
    capability: str,
    rarity: str,
    color_pref: str = "Classic Red",
    animal_pref: str = "Owl",
    style_vibe: str = "Cute & sparkly",
) -> Path:
    """
    Generate a fully text-to-image avatar via Microsoft's MAI-Image-2.5 model
    on Azure AI Foundry - no photo of the attendee is used or needed. The
    prompt varies by Pokemon-type (capability), rarity, and the person's fun
    color/animal/style picks, so each card looks distinct and personal
    without any personal/biometric data.

    API reference: https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-mai-image
    """
    if not MAI_ENDPOINT or not MAI_API_KEY:
        raise RuntimeError(
            "MAI_ENDPOINT / MAI_API_KEY not configured in environment_variables.env - "
            "cannot generate avatar image. See README for how to get these from the "
            "Foundry portal."
        )

    prompt = _build_avatar_prompt(capability, rarity, color_pref, animal_pref, style_vibe)
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
    result = response.json()

    image_entries = [entry for entry in result.get("data", []) if "b64_json" in entry]
    if not image_entries:
        raise RuntimeError(f"Unexpected response format from MAI-Image-2.5: {result}")

    image_bytes = base64.b64decode(image_entries[0]["b64_json"])
    raw_path = OUTPUT_FOLDER / f"{card_number}_raw.png"
    raw_path.write_bytes(image_bytes)

    fitted_path = OUTPUT_FOLDER / f"{card_number}_avatar.png"
    _fit_to_slot(raw_path, fitted_path, AVATAR_SLOT_SIZE)
    return fitted_path


def _fit_to_slot(src_path: Path, dst_path: Path, slot_size: tuple[int, int]) -> None:
    """Center-crop and resize an image to exactly fill `slot_size`."""
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


# --------------------------------------------------------------------------
# 3. Signature skill flavor text - unchanged logic from v1
# --------------------------------------------------------------------------

MAX_SKILL_TEXT_CHARS = 200


def generate_skill_text_rule_based(attack1: str, attack_text: str, attack2: str) -> str:
    text = f"{attack1} in daily work, striking with {attack2} when it really counts. {attack_text}"
    return text[:MAX_SKILL_TEXT_CHARS]


def generate_skill_text(ability: str, attack1: str, attack_text: str, attack2: str, use_ai: bool = True) -> str:
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
                    {
                        "role": "user",
                        "content": (
                            f"Ability: {ability}\n"
                            f"Daily approach: {attack1}\n"
                            f"Humor reference line: {attack_text}\n"
                            f"Signature move: {attack2}"
                        ),
                    },
                ],
                max_tokens=120,
                temperature=0.9,
            )
            text = (response.choices[0].message.content or "").strip()
            if text and len(text) <= MAX_SKILL_TEXT_CHARS + 20:
                return text[:MAX_SKILL_TEXT_CHARS]
        except (OpenAIError, Exception) as e:
            print(f"Skill text generation via LLM failed, falling back to rule-based: {e}")

    return generate_skill_text_rule_based(attack1, attack_text, attack2)


# --------------------------------------------------------------------------
# 4. Rarity & 5. Card counter - unchanged from v1
# --------------------------------------------------------------------------

def draw_rarity() -> str:
    tiers = list(RARITY_WEIGHTS.keys())
    weights = list(RARITY_WEIGHTS.values())
    return random.choices(tiers, weights=weights, k=1)[0]


def next_card_number() -> str:
    count = 1
    if COUNTER_FILE.exists():
        try:
            count = int(COUNTER_FILE.read_text().strip()) + 1
        except ValueError:
            count = 1
    COUNTER_FILE.write_text(str(count))
    return f"DA-{count:03d}"


# --------------------------------------------------------------------------
# 6. Pipeline orchestration
# --------------------------------------------------------------------------

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

    level_name = EVOLUTION_STAGES[answers.evolution]
    capability = POKEMON_TYPES[answers.type_]
    domain_tag = TYPE_DOMAIN_TAGS[capability]
    hp_flavor, hp_value = HP_TIERS[answers.hp]
    xp = round((hp_value - 90) / 80 * 1000)
    ability_name = ABILITIES[answers.ability]
    attack1_name = ATTACK_1[answers.attack1]
    attack_text_line = ATTACK_TEXT[answers.attack_text]
    attack2_name = ATTACK_2[answers.attack2]

    _report("🎲 Rolling for rarity...")
    rarity = draw_rarity()
    _report(f"You rolled **{rarity}**!")

    _report("🪄 Naming your data alter-ego...")
    pokemon_name = generate_name(answers.first_name, use_ai=use_ai)
    _report(f"Meet **{pokemon_name}**!")

    _report("✍️ Writing your signature skill...")
    skill_text = generate_skill_text(ability_name, attack1_name, attack_text_line, attack2_name, use_ai=use_ai)

    if use_ai:
        _report("🎨 Painting your data creature (this is the slow part, hang tight)...")
        avatar_path = generate_avatar(
            card_number, capability, rarity,
            color_pref=answers.color_pref, animal_pref=answers.animal_pref, style_vibe=answers.style_vibe,
        )
    else:
        avatar_path = OUTPUT_FOLDER / f"{card_number}_avatar_placeholder.png"
        Image.new("RGB", AVATAR_SLOT_SIZE, BRAND_RED).save(avatar_path)

    _report("🖼️ Assembling your card...")

    return CardData(
        card_number=card_number,
        pokemon_name=pokemon_name,
        level_name=level_name,
        xp=xp,
        hp_flavor=hp_flavor,
        hp_value=hp_value,
        capability=capability,
        domain_tag=domain_tag,
        skill_name=ability_name,
        skill_text=skill_text,
        progress_stage=answers.evolution,
        progress_label=_progress_label(answers.evolution),
        rarity=rarity,
        rarity_color=BRAND_RED,
        avatar_path=avatar_path,
    )


# --------------------------------------------------------------------------
# 7. Card composition (fixed template, PIL)
# --------------------------------------------------------------------------

def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """
    Load a font at the exact requested size. Tries the brand font first,
    then falls back to the bundled Poppins fonts (which DO respect the
    requested size, unlike PIL's built-in default font) so text is never
    tiny even if brand fonts haven't been added to assets/fonts/ yet.
    """
    candidates = [FONTS_FOLDER / name, FONTS_FOLDER / "brand-regular.ttf"]
    for path in candidates:
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            continue
    # Last-resort fallback - only reached if even the bundled font is
    # missing. Note this WILL ignore `size` and render tiny text; keep the
    # bundled fonts in place to avoid this path.
    return ImageFont.load_default()


def _font_bold(size: int) -> ImageFont.FreeTypeFont:
    return _load_font("brand-bold.ttf", size)


def _font_medium(size: int) -> ImageFont.FreeTypeFont:
    return _load_font("brand-medium.ttf", size)


def _font_regular(size: int) -> ImageFont.FreeTypeFont:
    return _load_font("brand-regular.ttf", size)


def _draw_outer_frame(draw: ImageDraw.ImageDraw, color: str) -> None:
    """Shared by front & back so the frame lines up when printed double-sided."""
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


def _draw_rarity_stamp(
    draw: ImageDraw.ImageDraw,
    right_x: float,
    y: float,
    rarity: str,
    filled_color: str,
    empty_color: str,
    text_color: str,
    font,
) -> None:
    """
    Draws a small right-aligned rarity indicator: the rarity name followed by
    5 diamonds, filled up to the rarity tier (1 for Common ... 5 for
    Mythic). This is the only place rarity shows up visually - it's
    intentionally the same size/style regardless of rarity, so nothing
    about the card's overall color or size changes between tiers.
    """
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


def compose_card_back(card: CardData, output_path: Optional[Path] = None) -> Path:
    output_path = output_path or (CARD_FOLDER / f"{card.card_number}_back.png")

    canvas = Image.new("RGB", (CARD_W, CARD_H), "#EDE9E6")
    draw = ImageDraw.Draw(canvas)
    _draw_outer_frame(draw, card.rarity_color)

    x = MARGIN + BORDER_WIDTH + 10
    right_x = CARD_W - MARGIN - BORDER_WIDTH - 10
    y = MARGIN + BORDER_WIDTH + 20

    # --- Level badge (top-left) & XP badge (top-right) ---
    badge_font = _font_medium(34)
    badge_h = 66
    draw.rounded_rectangle([x, y, x + 300, y + badge_h], radius=badge_h // 2, fill="#D8D3CF")
    draw.text((x + 26, y + badge_h // 2), card.level_name, font=badge_font, fill="black", anchor="lm")

    xp_text = f"{card.xp} XP"
    xp_w = 190
    draw.rounded_rectangle([right_x - xp_w, y, right_x, y + badge_h], radius=badge_h // 2, fill="#D8D3CF")
    draw.text((right_x - xp_w / 2, y + badge_h // 2), xp_text, font=badge_font, fill="black", anchor="mm")

    # --- Rarity indicator (diamonds, not a color scheme) ---
    _draw_rarity_stamp(
        draw, right_x, y + badge_h + 30, card.rarity,
        filled_color=card.rarity_color, empty_color="#DEDAD6", text_color="black",
        font=_font_medium(26),
    )

    y += badge_h + 66

    # --- Title (Pokemon name) ---
    title_font = _font_bold(78)
    draw.text((x, y), card.pokemon_name, font=title_font, fill="black")
    y += 100

    # --- Capability line ---
    cap_font = _font_medium(38)
    domain_font = _font_regular(26)
    draw.ellipse([x, y + 6, x + 30, y + 36], fill=card.rarity_color)
    draw.text((x + 44, y), card.capability, font=cap_font, fill="black")
    cap_w = draw.textlength(card.capability, font=cap_font)
    draw.text((x + 44 + cap_w + 16, y + 8), card.domain_tag.upper(), font=domain_font, fill="#8A8886")
    y += 66

    # --- Avatar photo slot ---
    slot_side = 620
    avatar = Image.open(card.avatar_path).convert("RGB").resize((slot_side, slot_side), Image.Resampling.LANCZOS)
    avatar_x = (CARD_W - slot_side) // 2
    canvas.paste(avatar, (avatar_x, y))
    draw.rectangle([avatar_x, y, avatar_x + slot_side, y + slot_side], outline=card.rarity_color, width=4)
    y += slot_side + 34

    # --- Signature skill block ---
    label_font = _font_bold(32)
    skill_name_font = _font_bold(54)
    body_font = _font_regular(34)

    draw.rectangle([x, y, x + 12, y + 40], fill=card.rarity_color)
    draw.text((x + 26, y), "SIGNATURE SKILL", font=label_font, fill=card.rarity_color)
    y += 50
    draw.text((x, y), card.skill_name, font=skill_name_font, fill="black")
    y += 68
    draw.line([x, y, right_x, y], fill="black", width=3)
    y += 20

    y = _draw_wrapped_text(draw, card.skill_text, (x, y), body_font, right_x - x, max_lines=4)

    # --- Progress section (pinned near the bottom) ---
    progress_y = CARD_H - MARGIN - 190
    draw.text((x, progress_y), "PROGRESS", font=label_font, fill=card.rarity_color)
    dot_y = progress_y + 50
    dot_x = x
    dot_d = 40
    for i in range(5):
        fill = card.rarity_color if i < card.progress_stage else "#DEDAD6"
        draw.ellipse([dot_x, dot_y, dot_x + dot_d, dot_y + dot_d], fill=fill)
        dot_x += dot_d + 14

    pill_w = 230
    draw.rounded_rectangle([right_x - pill_w, dot_y - 8, right_x, dot_y + dot_d + 8], radius=dot_d, fill=card.rarity_color)
    draw.text((right_x - pill_w / 2, dot_y + dot_d / 2), card.progress_label, font=_font_medium(30), fill="white", anchor="mm")

    # --- Card number (bottom) ---
    number_y = CARD_H - MARGIN - 60
    draw.text((x, number_y), card.card_number, font=body_font, fill="black")
    draw.line([x + 190, number_y + 22, right_x, number_y + 22], fill="black", width=2)

    canvas.save(output_path, dpi=(DPI, DPI))
    card.card_back_path = output_path
    return output_path


def _draw_wrapped_text(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], font, max_width: int, max_lines: int = 6) -> int:
    """Draws wrapped text and returns the y-coordinate just below the last line."""
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
    Static card front, rendered once per rarity tier and cached under
    assets/. This generates a placeholder programmatically so the pipeline
    is testable before final brand artwork exists - once you have real
    front designs, drop pre-made PNGs at assets/front_<rarity>.png (exact
    size CARD_W x CARD_H at 300dpi) and this function will use those
    instead automatically.

    IMPORTANT while iterating on the design/fonts: this caches its output
    per rarity (and per FRONT_DESIGN_VERSION, see top of file) and reuses
    it on every later call. Bump FRONT_DESIGN_VERSION whenever you change
    this function so old cached files stop being picked up automatically -
    or pass force=True to regenerate on demand without bumping it.
    """
    cached = ASSETS_FOLDER / f"front_{rarity.lower()}_{FRONT_DESIGN_VERSION}.png"
    if cached.exists() and output_path is None and not force:
        return cached

    output_path = output_path or cached

    canvas = Image.new("RGB", (CARD_W, CARD_H), BRAND_RED)
    draw = ImageDraw.Draw(canvas)
    _draw_outer_frame(draw, "white")

    brand_font = _font_bold(96)
    tagline_font = _font_medium(44)
    sub_font = _font_regular(30)

    draw.text((CARD_W // 2, int(CARD_H * 0.22)), "BearingPoint", font=brand_font, fill="white", anchor="mm")
    draw.line([MARGIN + 60, int(CARD_H * 0.29), CARD_W - MARGIN - 60, int(CARD_H * 0.29)], fill="white", width=3)

    draw.text((CARD_W // 2, int(CARD_H * 0.85)), "Collect. Learn. Grow.", font=tagline_font, fill="white", anchor="mm")
    draw.text((CARD_W // 2, int(CARD_H * 0.90)), "Data Expo Series", font=sub_font, fill="white", anchor="mm")

    # --- Rarity indicator (diamonds, not a color scheme) - same small
    # stamp as on the back, so rarity is still visible on the front without
    # changing the card's color at all.
    _draw_rarity_stamp(
        draw, CARD_W - MARGIN - BORDER_WIDTH - 20, int(CARD_H * 0.955), rarity,
        filled_color="white", empty_color="#E8AAB2", text_color="white",
        font=_font_medium(26),
    )

    canvas.save(output_path, dpi=(DPI, DPI))
    return output_path


# --------------------------------------------------------------------------
# TEST EXAMPLES - run this file directly to test the pipeline without the
# Streamlit UI or any API keys.
# --------------------------------------------------------------------------

if __name__ == "__main__":
    TEST_USE_AI = False  # flip to True once MAI_ENDPOINT/MAI_API_KEY (and optionally OPENAI_API_KEY) are set

    example_answers = QuestionnaireAnswers(
        first_name="Jasper",
        evolution=3,
        type_=5,
        hp=4,
        ability=5,
        attack1=3,
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
        "xp": card.xp,
        "capability": card.capability,
        "domain_tag": card.domain_tag,
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
