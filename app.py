"""
Streamlit questionnaire for the Data Expo avatar card generator (v6).

Changes vs v5:
- Bilingual: a language switcher at the top (English / Nederlands) drives
  every piece of UI text, including the questions and the "just for fun"
  answer options. The underlying data (color/animal/vibe/scenario values
  fed into card_pipeline) always stays the canonical English string
  regardless of displayed language, since that's what the avatar prompt
  and card logic expect - only the *label* the person sees is translated,
  resolved back to the English value by matching list position.
- Brand-compliant theming: G20 (#E6DEDA) background instead of white,
  black-on-red hero band instead of white-on-red, per brand guidelines.
- Updated, more active intro copy.
- Note on terminology: this app/codebase calls the branded static
  BearingPoint side "front" (compose_card_front) and the personalized
  stats/avatar side "back" (compose_card_back) - but the physical card
  convention (and this file's on-screen labels) has it the other way
  around: the stats/avatar side is shown first and labeled "Front", the
  branded side second and labeled "Back". That's a display-only relabeling
  here; the Python variable/function names in card_pipeline.py were not
  renamed to avoid a much larger, riskier refactor - flag it if you'd
  like that cleaned up too.

Run with:

    streamlit run app.py

Requires MAI_ENDPOINT / MAI_API_KEY (avatar) in environment_variables.env
for real generation, and optionally OPENAI_API_KEY (name/skill text -
falls back to rule-based logic if unset).
"""

from pathlib import Path

import streamlit as st

from card_pipeline import (
    ANIMAL_PREF_OPTIONS,
    COLOR_PREF_OPTIONS,
    STYLE_VIBE_OPTIONS,
    QuestionnaireAnswers,
    build_card_data,
    compose_card_back,
    compose_card_front,
)
from print_utils import print_card

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "assets" / "logo.png"  # drop your real BearingPoint logo file here

st.set_page_config(page_title="Data Expo Avatar Card", page_icon="✨", layout="centered")

BRAND_RED = "#FF3D47"
G20 = "#E6DEDA"

# --------------------------------------------------------------------------
# Translations
# --------------------------------------------------------------------------

TEXT = {
    "en": {
        "lang_choice": "🇬🇧 English",
        "logo_hint": "💡 Add your logo at assets/logo.png to have it appear above the title.",
        "hero_title": "✨ Create your Data Avatar Card",
        "hero_subtitle": (
            "Would you like to discover which data creature you are? Answer a few short "
            "questions and watch your unique data creature come to life."
        ),
        "first_name": "First name",
        "stats_title": "How much is this... you?",
        "stats_caption": "Rate each statement - your data persona gets revealed on the card afterwards 👀",
        "q_evolution": "I've basically seen every kind of data disaster there is.",
        "q_scenario_title": "It's 5pm on a Friday and the data just broke. What's your first move?",
        "q_hp": "Last-minute chaos and changing requirements don't really rattle me.",
        "q_ability": "People randomly come find me when they're stuck on something data-related.",
        "q_attack_text": "I can laugh about the daily chaos of working with data.",
        "q_attack2": "I'd rather brainstorm it out loud with the team than solve it alone in silence.",
        "fun_title": "Just for fun",
        "fun_caption": "These don't affect your stats - they just shape what your avatar looks like.",
        "color_label": "Pick a color that feels like you",
        "animal_label": "Pick a spirit animal for your avatar",
        "vibe_label": "Pick a vibe",
        "use_ai_label": "Use AI generation (name / avatar / skill text)",
        "use_ai_help": (
            "Untick to quickly test the layout using rule-based fallbacks and a solid "
            "placeholder avatar, without calling any API."
        ),
        "submit": "Generate my card ✨",
        "error_no_name": "Please fill in your first name.",
        "generating_status": "Brewing your data avatar...",
        "generating_done": "Card {n} ready!",
        "success_msg": "Card {n} generated — Rarity: {r}",
        "front_caption": "Front",
        "back_caption": "Back",
        "details_expander": "Card details",
        "details_keys": {
            "name": "Name", "level": "Level", "xp": "XP", "capability": "Capability",
            "skill_name": "Signature skill", "skill_move": "Signature move", "skill_text": "Skill text",
            "progress": "Progress", "rarity": "Rarity", "card_number": "Card number",
        },
        "print_button": "🖨️ Print this card",
        "print_success": "Sent to printer!",
        "agreement_labels": {1: "Not me at all", 2: "A little bit", 3: "Somewhat", 4: "Pretty much", 5: "100% me"},
        "scenario_options": [
            'Panic slightly, then Google "what is a pipeline"',
            "Quietly patch it before anyone even notices",
            "Make sure everything gets logged, labeled, and properly filed away",
            "Start digging for the pattern hiding behind the mess",
            "Get weirdly excited - this is a great case study for a model",
            "Ask the newest AI tool to just fix it for you",
        ],
        "color_options": COLOR_PREF_OPTIONS,
        "animal_options": ANIMAL_PREF_OPTIONS,
        "vibe_options": STYLE_VIBE_OPTIONS,
    },
    "nl": {
        "lang_choice": "🇳🇱 Nederlands",
        "logo_hint": "💡 Voeg je logo toe op assets/logo.png om het boven de titel te tonen.",
        "hero_title": "✨ Maak jouw Data Avatar Kaart",
        "hero_subtitle": (
            "Wil je ontdekken welk data-wezen jij bent? Beantwoord een paar korte vragen "
            "en zie jouw unieke data-wezen tot leven komen."
        ),
        "first_name": "Voornaam",
        "stats_title": "Hoeveel is dit... jou?",
        "stats_caption": "Beoordeel elke stelling - je data-persona wordt straks onthuld op de kaart 👀",
        "q_evolution": "Ik heb zo'n beetje elke data-ramp al meegemaakt.",
        "q_scenario_title": "Het is vrijdag 17:00 en de data is zojuist gecrasht. Wat doe je als eerste?",
        "q_hp": "Last-minute chaos en veranderende eisen brengen mij niet snel van mijn stuk.",
        "q_ability": "Mensen komen me spontaan opzoeken als ze vastlopen op iets met data.",
        "q_attack_text": "Ik kan lachen om de dagelijkse chaos van het werken met data.",
        "q_attack2": "Ik brainstorm liever hardop met het team dan het in stilte alleen op te lossen.",
        "fun_title": "Puur voor de lol",
        "fun_caption": "Deze hebben geen invloed op je statistieken - ze bepalen alleen hoe je avatar eruitziet.",
        "color_label": "Kies een kleur die bij je past",
        "animal_label": "Kies een spirit-dier voor je avatar",
        "vibe_label": "Kies een vibe",
        "use_ai_label": "Gebruik AI-generatie (naam / avatar / vaardigheidstekst)",
        "use_ai_help": (
            "Vink uit om snel de layout te testen met vaste teksten en een effen "
            "placeholder-avatar, zonder API-aanroepen."
        ),
        "submit": "Genereer mijn kaart ✨",
        "error_no_name": "Vul je voornaam in.",
        "generating_status": "Je data-avatar wordt gebrouwen...",
        "generating_done": "Kaart {n} is klaar!",
        "success_msg": "Kaart {n} gegenereerd — Zeldzaamheid: {r}",
        "front_caption": "Voorkant",
        "back_caption": "Achterkant",
        "details_expander": "Kaartdetails",
        "details_keys": {
            "name": "Naam", "level": "Niveau", "xp": "XP", "capability": "Vaardigheidstype",
            "skill_name": "Signatuurvaardigheid", "skill_move": "Signatuurmove", "skill_text": "Vaardigheidstekst",
            "progress": "Voortgang", "rarity": "Zeldzaamheid", "card_number": "Kaartnummer",
        },
        "print_button": "🖨️ Print deze kaart",
        "print_success": "Naar de printer gestuurd!",
        "agreement_labels": {1: "Helemaal niet mij", 2: "Een beetje", 3: "Enigszins", 4: "Best wel", 5: "100% mij"},
        "scenario_options": [
            'Licht in paniek raken en dan googelen "wat is een pipeline"',
            "Het rustig repareren voordat iemand het doorheeft",
            "Zorgen dat alles netjes gelogd, gelabeld en gearchiveerd wordt",
            "Op zoek gaan naar het patroon achter de chaos",
            "Verrassend enthousiast worden - top casestudy voor een model",
            "De nieuwste AI-tool vragen om het gewoon op te lossen",
        ],
        "color_options": ["Elektrisch Blauw", "Zonsondergang Oranje", "Neon Groen", "Koninklijk Paars", "Klassiek Rood"],
        "animal_options": ["Uil", "Vos", "Draak", "Kat", "Robotkonijn"],
        "vibe_options": ["Schattig & sprankelend", "Strak & futuristisch", "Gedurfd & fel", "Rustig & zen", "Retro & funky"],
    },
}

# --------------------------------------------------------------------------
# Language switcher - at the very top, persisted in session_state
# --------------------------------------------------------------------------
if "lang" not in st.session_state:
    st.session_state["lang"] = "en"

lang_choice = st.radio(
    "Language / Taal",
    options=["en", "nl"],
    format_func=lambda v: TEXT[v]["lang_choice"],
    horizontal=True,
    key="lang",
    label_visibility="collapsed",
)
T = TEXT[lang_choice]

# --------------------------------------------------------------------------
# BearingPoint-style theming - G20 background, black-on-red hero (no more
# white-on-red), matches the finalized card design.
# --------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: {G20};
    }}
    h1, h2, h3 {{
        color: {BRAND_RED};
    }}
    div.stButton > button, div.stFormSubmitButton > button {{
        background-color: {BRAND_RED};
        color: black;
        border: none;
        border-radius: 999px;
        padding: 0.6em 1.6em;
        font-weight: 600;
    }}
    div.stButton > button:hover, div.stFormSubmitButton > button:hover {{
        background-color: #e3323c;
        color: black;
    }}
    [data-testid="stSlider"] [role="slider"] {{
        background-color: {BRAND_RED} !important;
    }}
    [data-testid="stProgress"] > div > div > div {{
        background-color: {BRAND_RED};
    }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: white;
        border-radius: 16px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Hero header
# --------------------------------------------------------------------------
if LOGO_PATH.exists():
    logo_col, _ = st.columns([1, 3])
    with logo_col:
        st.image(str(LOGO_PATH), width=180)
else:
    st.markdown(f"<div style='font-weight:700; font-size:1.3em; color:{BRAND_RED};'>BearingPoint</div>", unsafe_allow_html=True)
    st.caption(T["logo_hint"])

st.markdown(
    f"""
    <div style="background:{BRAND_RED}; padding:2em 1.5em; border-radius:20px;
                text-align:center; margin-bottom:1.5em;
                box-shadow:0 10px 28px rgba(255,61,71,0.30);">
        <h1 style="color:black; margin:0; font-size:2.1em;">{T['hero_title']}</h1>
        <p style="color:black; opacity:0.85; margin-top:0.6em; margin-bottom:0; font-size:1.05em;">
            {T['hero_subtitle']}
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


def agreement_slider(label: str, key: str) -> int:
    labels = T["agreement_labels"]
    return st.select_slider(label, options=[1, 2, 3, 4, 5], value=3, format_func=lambda v: labels[v], key=key)


with st.form("questionnaire"):
    first_name = st.text_input(T["first_name"])

    with st.container(border=True):
        st.subheader(T["stats_title"])
        st.caption(T["stats_caption"])

        evolution = agreement_slider(T["q_evolution"], "evolution")

        st.markdown(f"**{T['q_scenario_title']}**")
        type_choice = st.radio(
            "type_scenario", T["scenario_options"], key="type_", label_visibility="collapsed",
        )
        type_ = T["scenario_options"].index(type_choice) + 1

        hp = agreement_slider(T["q_hp"], "hp")
        ability = agreement_slider(T["q_ability"], "ability")
        attack_text = agreement_slider(T["q_attack_text"], "attack_text")
        attack2 = agreement_slider(T["q_attack2"], "attack2")

    with st.container(border=True):
        st.subheader(T["fun_title"])
        st.caption(T["fun_caption"])

        color_choice = st.radio(T["color_label"], T["color_options"], horizontal=True)
        color_pref = COLOR_PREF_OPTIONS[T["color_options"].index(color_choice)]

        animal_choice = st.radio(T["animal_label"], T["animal_options"], horizontal=True)
        animal_pref = ANIMAL_PREF_OPTIONS[T["animal_options"].index(animal_choice)]

        vibe_choice = st.radio(T["vibe_label"], T["vibe_options"], horizontal=True)
        style_vibe = STYLE_VIBE_OPTIONS[T["vibe_options"].index(vibe_choice)]

    use_ai = st.checkbox(T["use_ai_label"], value=True, help=T["use_ai_help"])

    submitted = st.form_submit_button(T["submit"])

if submitted:
    if not first_name:
        st.error(T["error_no_name"])
        st.stop()

    answers = QuestionnaireAnswers(
        first_name=first_name,
        evolution=evolution,
        type_=type_,
        hp=hp,
        ability=ability,
        attack_text=attack_text,
        attack2=attack2,
        color_pref=color_pref,
        animal_pref=animal_pref,
        style_vibe=style_vibe,
    )

    # Steps reported by build_card_data's progress_callback, in order - used
    # to drive a real percentage instead of an indeterminate spinner. The
    # avatar-generation step is skipped (and thus not counted) when AI is off.
    total_steps = 8 if use_ai else 7
    step_count = {"n": 0}

    with st.container(border=True):
        progress_bar = st.progress(0)
        caption_ph = st.empty()

        def _on_progress(msg: str) -> None:
            step_count["n"] += 1
            pct = min(int(step_count["n"] / total_steps * 100), 100)
            progress_bar.progress(pct)
            caption_ph.markdown(f"**{msg}**")

        card = build_card_data(answers, use_ai=use_ai, progress_callback=_on_progress)
        # NB: card_pipeline calls the branded static side "front" and the
        # stats/avatar side "back" - displayed in reverse below to match
        # the team's physical-card convention (stats side = front).
        branded_path = compose_card_front(card.rarity)
        stats_path = compose_card_back(card)

        progress_bar.progress(100)
        caption_ph.markdown(f"**{T['generating_done'].format(n=card.card_number)}**")

    st.session_state["card"] = card
    st.session_state["stats_path"] = stats_path
    st.session_state["branded_path"] = branded_path
    st.balloons()

if "card" in st.session_state:
    card = st.session_state["card"]
    stats_path = st.session_state["stats_path"]
    branded_path = st.session_state["branded_path"]

    st.success(T["success_msg"].format(n=card.card_number, r=card.rarity))

    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            st.image(str(stats_path), caption=T["front_caption"])
        with col2:
            st.image(str(branded_path), caption=T["back_caption"])

    with st.expander(T["details_expander"]):
        k = T["details_keys"]
        st.write(
            {
                k["name"]: card.pokemon_name,
                k["level"]: card.level_name,
                k["xp"]: card.xp,
                k["capability"]: f"{card.capability} ({card.domain_tag})",
                k["skill_name"]: card.skill_name,
                k["skill_move"]: card.signature_move,
                k["skill_text"]: card.skill_text,
                k["progress"]: f"{card.progress_stage}/5 ({card.progress_label})",
                k["rarity"]: card.rarity,
                k["card_number"]: card.card_number,
            }
        )

    if st.button(T["print_button"]):
        try:
            print_card(str(branded_path), str(stats_path))
            st.success(T["print_success"])
        except RuntimeError as e:
            st.error(str(e))

st.markdown(
    "<div style='text-align:center; color:#98847A; margin-top:2em; font-size:0.85em;'>"
    "BearingPoint · Data Expo Series</div>",
    unsafe_allow_html=True,
)
