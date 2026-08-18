"""
Data Expo Avatar Card - Game Rules Engine
==========================================

This module IS the game behind the cards. It's kept deliberately separate
from card_pipeline.py (which handles AI calls, image composition, and
printing) for two reasons:

1. Readability - all the "what turns into what" design decisions live in
   one place, instead of being scattered between dict definitions and
   inline computation halfway through an orchestration function.
2. Testability - everything here is pure and deterministic (the only
   randomness is the rarity roll, which is randomness *by design* - see
   RARITY_WEIGHTS). No network calls, no file I/O, no image generation.
   You can unit-test the entire scoring system without mocking anything.

The flow, end to end:

    QuestionnaireAnswers  --resolve_game()-->  GameResult
    GameResult + fun picks  --build_avatar_prompt()-->  a text prompt for MAI-Image-2.5

Design principle for every table below: every questionnaire answer should
map to exactly ONE clearly visible, undiluted card element, and every
result should make internal sense next to the others (see "Logical
consistency notes" throughout). If you add a new question, ask first:
"what single, distinct thing on the card will this control?" - if you
don't have a clean answer, the question probably doesn't pull its weight.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


# --------------------------------------------------------------------------
# Questionnaire input
# --------------------------------------------------------------------------

@dataclass
class QuestionnaireAnswers:
    first_name: str
    evolution: int   # 1-5  -> Level + Progress bar
    type_: int        # 1-6  -> Capability/domain + avatar theme (scenario question, see app.py)
    hp: int           # 1-5  -> HP stat + avatar energy
    ability: int      # 1-5  -> Signature Skill name
    attack_text: int  # 1-5  -> Signature Skill flavor text (humor seed)
    attack2: int      # 1-5  -> Signature Move
    # Fun personalization - purely cosmetic, only used to flavor the avatar
    # image prompt. Doesn't affect Level/HP/Capability/etc. at all.
    color_pref: str = "Classic Red"
    animal_pref: str = "Owl"
    style_vibe: str = "Cute & sparkly"

    def __post_init__(self):
        for name in ("evolution", "hp", "ability", "attack_text", "attack2"):
            value = getattr(self, name)
            if value not in (1, 2, 3, 4, 5):
                raise ValueError(f"{name} must be 1-5, got {value}")
        if self.type_ not in (1, 2, 3, 4, 5, 6):
            raise ValueError(f"type_ must be 1-6, got {self.type_}")


@dataclass
class GameResult:
    """Everything the game rules determine from a set of answers, before
    any AI generation (name/avatar/flavor text) or rendering happens."""
    level_name: str
    capability: str
    domain_tag: str
    hp_value: int
    hp_flavor: str
    skill_name: str
    attack_text_line: str
    signature_move: str
    rarity: str
    progress_stage: int
    progress_label: str


# --------------------------------------------------------------------------
# 1. Evolution (experience) -> Level badge + Progress bar
# --------------------------------------------------------------------------

EVOLUTION_STAGES = {
    1: "Data Sprout",
    2: "Data Scout",
    3: "Data Voyager",
    4: "Data Master",
    5: "Data Legend",
}


def _progress_label(stage: int) -> str:
    if stage <= 2:
        return "starter"
    if stage == 3:
        return "skilled"
    return "expert"


# --------------------------------------------------------------------------
# 2. Type/domain scenario -> Capability + domain tag + avatar theme
#
# A single spectrum from "foundational/structural" to "cutting-edge/
# exploratory" work, matching how these data facets actually relate in the
# real world - not six unrelated categories bolted together. The question
# in app.py is framed as a scenario ("what's your first move when data
# breaks"), not a slider, since "which domain are you" is categorical, not
# a matter of degree - but the underlying 1-6 mapping below is still a
# coherent spectrum for consistency with the rest of the scoring system.
# --------------------------------------------------------------------------

POKEMON_TYPES = {
    1: "Data Noob",
    2: "Pipeline Fox",
    3: "Data Guardian",
    4: "Insight Owl",
    5: "Pattern Seeker",
    6: "AI Sprinter",
}

TYPE_DOMAIN_TAGS = {
    "Data Noob": "Just Getting Started",
    "Pipeline Fox": "Data Engineering",
    "Data Guardian": "Data Management",
    "Insight Owl": "Analytics & BI",
    "Pattern Seeker": "Data Science",
    "AI Sprinter": "AI & ML",
}

# Personality/pose hint per type - what the creature is DOING, tied to the
# real activity of that domain (archiving, pattern-spotting, pipeline
# work...), not a generic personality adjective.
TYPE_VISUAL_HINTS = {
    "Data Noob": "a bewildered creature clutching a giant coffee mug, surrounded by an intimidating stack of unopened spreadsheets",
    "Pipeline Fox": "a calm, capable creature quietly patching a leaking pipe or conveyor belt before anyone even notices",
    "Data Guardian": "a meticulous creature carefully filing glowing folders and labels into neat, orderly archive boxes",
    "Insight Owl": "a sharp-eyed creature tracing a glowing trend line rising up out of a messy cloud of scattered dots",
    "Pattern Seeker": "an excited creature surrounded by floating puzzle-piece-shaped fragments it's assembling into a hidden formula",
    "AI Sprinter": "a creature reaching eagerly toward a glowing holographic 'NEW' button, leaving a trail of light behind it",
}

# The actual environment/scene behind the creature, per type - this is
# what makes the avatar read as "Pokemon card art" instead of an icon
# floating in empty space: a believable place, not just a gradient.
TYPE_ENVIRONMENTS = {
    "Data Noob": "a cluttered desk scene with towering stacks of oversized printouts and empty coffee cups fading into the background",
    "Pipeline Fox": "an industrial pipeline workshop, glowing pipes and conveyor belts stretching off into the background",
    "Data Guardian": "a vault-like archive room, rows of neatly labeled glowing folders on tall shelves fading into the distance",
    "Insight Owl": "a dim analyst room, a wall of glowing dashboards and charts filling the background",
    "Pattern Seeker": "a night-sky-like backdrop of glowing constellation dots connected by faint lines",
    "AI Sprinter": "a futuristic digital speed-tunnel of streaming light trails and floating data particles",
}


# --------------------------------------------------------------------------
# 3. HP (resilience under chaos) -> HP stat + avatar energy
#
# Logical consistency note: this used to be relabeled "XP" and rescaled to
# a 0-1000 number, sitting right next to the Level badge - which strongly
# implied XP feeds Level, the way it does in an actual RPG. It doesn't:
# Level comes from the evolution question, HP comes from this completely
# separate resilience question. Showing the raw HP value (90-170, matching
# the original brief) under its own honest "HP" label removes that false
# implied link instead of dressing an unrelated stat up as fake XP.
# --------------------------------------------------------------------------

HP_TIERS = {
    1: ("Calm Builder", 90),
    2: ("Steady Planner", 110),
    3: ("Data Beaver", 130),
    4: ("Chaos Tamer", 150),
    5: ("Deadline Dragon", 170),
}

HP_VISUAL_HINTS = {
    "Calm Builder": "a relaxed, unhurried energy, moving at its own steady pace",
    "Steady Planner": "a composed, prepared energy, like it already saw this coming",
    "Data Beaver": "a busy, industrious energy, mid-task and building something",
    "Chaos Tamer": "a confident energy, calmly standing in the middle of a small storm",
    "Deadline Dragon": "an intense, high-energy pose, thriving right at the edge of the deadline",
}


# --------------------------------------------------------------------------
# 4. Ability -> Signature Skill name
# --------------------------------------------------------------------------

ABILITIES = {
    1: "Sharp Eye",
    2: "Bright Spark",
    3: "Helping Hand",
    4: "Problem Catcher",
    5: "Data Whisperer",
}


# --------------------------------------------------------------------------
# 5. Humor statement -> Signature Skill flavor text (sole input now - see
# card_pipeline.generate_skill_text; no longer diluted by blending in
# 2-3 other unrelated answers, so the text stays traceable to what the
# person actually rated highest).
# --------------------------------------------------------------------------

ATTACK_TEXT = {
    1: "Discover one hidden insight in the data. Nobody knew it existed, but you found it in five minutes.",
    2: "Bring order to a messy dataset. Even the column names thank you personally.",
    3: "This attack deals 10 extra damage for every KPI that is actually being used thanks to you.",
    4: "Discover an opportunity before anyone else spots it.",
    5: 'If a stakeholder says, "That\'s exactly what I meant," double the damage of this attack.',
}


# --------------------------------------------------------------------------
# 6. Team-brainstorm vs. solo -> Signature Move
#
# Logical consistency note: the question ("I'd rather brainstorm out loud
# with the team than solve it alone in silence") means HIGH agreement =
# most collaborative. Tier 5 must therefore be the most collaborative
# name and tier 1 the most solo one - this was previously backwards
# (tier 5 was "Hero Mode", a solo callback), which directly contradicted
# what a high score was supposed to mean.
# --------------------------------------------------------------------------

ATTACK_2 = {
    1: "Hero Mode",           # solo - "appears exactly when things get critical"
    2: "Dataflow Inferno",
    3: "Alignment Cannon",
    4: "Workshop Whirlwind",
    5: "Brainstorm Cyclone",  # collaborative - "brings all ideas together"
}


# --------------------------------------------------------------------------
# 7. Rarity - pure chance, independent of every answer by design (matches
# the original brief: "puur geluk" / pure luck). Communicated via a small
# diamond stamp, not a card color - see card_pipeline._draw_rarity_stamp.
# --------------------------------------------------------------------------

RARITY_WEIGHTS = {
    "Common": 50,
    "Rare": 30,
    "Epic": 15,
    "Legendary": 4,
    "Mythic": 1,
}

RARITY_TIER_INDEX = {
    "Common": 1,
    "Rare": 2,
    "Epic": 3,
    "Legendary": 4,
    "Mythic": 5,
}

# Atmosphere/lighting flair layered into the avatar, not a color change -
# the color palette is always driven by color_pref (see build_avatar_prompt).
RARITY_VISUAL_HINTS = {
    "Common": "a simple, clean design",
    "Rare": "a subtle soft glowing aura",
    "Epic": "ornate glowing patterns and small floating data-sparkles around it",
    "Legendary": "a radiant magical aura with dramatic rim lighting",
    "Mythic": "an extraordinary, almost mythical presence with intricate glowing linework and dramatic atmosphere",
}


def draw_rarity() -> str:
    tiers = list(RARITY_WEIGHTS.keys())
    weights = list(RARITY_WEIGHTS.values())
    return random.choices(tiers, weights=weights, k=1)[0]


# --------------------------------------------------------------------------
# Fun, purely cosmetic questionnaire options - only flavor the avatar
# image prompt. Nothing here touches Level/HP/Capability/etc.
# --------------------------------------------------------------------------

COLOR_PREF_OPTIONS = ["Electric Blue", "Sunset Orange", "Neon Green", "Royal Purple", "Classic Red"]
ANIMAL_PREF_OPTIONS = ["Owl", "Fox", "Dragon", "Cat", "Robot Bunny"]
STYLE_VIBE_OPTIONS = ["Cute & sparkly", "Sleek & futuristic", "Bold & fierce", "Calm & zen", "Retro & funky"]


# --------------------------------------------------------------------------
# The single entry point: answers in, fully-determined game result out.
# --------------------------------------------------------------------------

def resolve_game(answers: QuestionnaireAnswers) -> GameResult:
    capability = POKEMON_TYPES[answers.type_]
    hp_flavor, hp_value = HP_TIERS[answers.hp]

    return GameResult(
        level_name=EVOLUTION_STAGES[answers.evolution],
        capability=capability,
        domain_tag=TYPE_DOMAIN_TAGS[capability],
        hp_value=hp_value,
        hp_flavor=hp_flavor,
        skill_name=ABILITIES[answers.ability],
        attack_text_line=ATTACK_TEXT[answers.attack_text],
        signature_move=ATTACK_2[answers.attack2],
        rarity=draw_rarity(),
        progress_stage=answers.evolution,
        progress_label=_progress_label(answers.evolution),
    )


# --------------------------------------------------------------------------
# Avatar prompt - turns a GameResult + fun picks into a MAI-Image-2.5 prompt.
#
# Design goals here specifically (per user feedback):
# - Read like actual Pokemon trading-card art: a bold, dynamic character
#   filling most of the frame, not a small icon floating in empty space.
# - The background is a real, themed environment (TYPE_ENVIRONMENTS) that
#   plays an active part in the image, not a blank margin - which also
#   means the character naturally fills the card's (now much bigger)
#   avatar slot instead of leaving awkward empty space around it.
# - color/animal/style still lead and stay dominant (see prior fix - the
#   old fixed suffix was so prescriptive it drowned out personalization).
# --------------------------------------------------------------------------

AVATAR_STYLE_SUFFIX = (
    "Rendered like official Pokemon trading-card art: a bold, dynamic illustrated "
    "character in an active pose, filling most of the square frame - not a small "
    "icon floating in empty space. The background is a real environment (described "
    "below), rendered with painterly depth and lighting so it plays an active part "
    "in the image instead of being a flat empty margin, while the character stays "
    "the clear focal point in the foreground. It does not need to look soft, cute, "
    "or fluffy - let it be sleek, tough, elegant, or quirky, whatever the vibe below "
    "calls for. Original design only - NOT a real person, NOT any existing "
    "copyrighted character or franchise. Square composition, no text, no logos, no "
    "watermarks, professional-event appropriate."
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


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def build_avatar_prompt(result: GameResult, color_pref: str, animal_pref: str, style_vibe: str) -> str:
    """
    Personalization (animal/color/style) leads the prompt and is stated in
    strong, unambiguous terms, since those are the only inputs that should
    make each avatar look genuinely different from the next. The
    type/rarity/HP hints stay secondary "personality/flair" notes so they
    nudge the mood and setting without competing with animal/color/style
    for what the model actually renders.
    """
    type_hint = TYPE_VISUAL_HINTS.get(result.capability, "a friendly data creature")
    environment = TYPE_ENVIRONMENTS.get(result.capability, "a softly lit, abstract data-themed backdrop")
    rarity_hint = RARITY_VISUAL_HINTS.get(result.rarity, "a simple, clean design")
    hp_hint = HP_VISUAL_HINTS.get(result.hp_flavor, "a calm, confident energy")
    data_motif = random.choice(DATA_MOTIF_OPTIONS)
    article = _article(animal_pref)

    return (
        f"Design an original character avatar clearly and recognizably based on {article} "
        f"{animal_pref.lower()} - keep its signature {animal_pref.lower()} features (silhouette, "
        f"ears/wings/tail, face shape) clearly readable, reimagined as a bold illustrated character. "
        f"Its color palette must be unmistakably {color_pref.lower()} - that color should be the "
        f"dominant hue covering most of its body/fur/scales/skin, not a small accent. "
        f"Give it one specific, fun data-themed design detail: {data_motif}. "
        f"Place it in this setting, visible in the background behind the character: {environment}. "
        f"Overall mood and styling: {style_vibe.lower()} - let this genuinely shape its attitude, "
        f"expression, and pose; it should not default to cute or fluffy unless this vibe calls for it. "
        f"Let its pose and expression also carry a hint of this personality trait: {type_hint}. "
        f"Its overall energy level: {hp_hint}. "
        f"Rarity flair layered into the lighting/atmosphere, without changing the color palette above: {rarity_hint}. "
        f"{AVATAR_STYLE_SUFFIX}"
    )
