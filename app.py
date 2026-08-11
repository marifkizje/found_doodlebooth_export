"""
Streamlit questionnaire for the Data Expo avatar card generator (v5).

Changes vs v4:
- A real progress bar (st.progress) drives the loading experience instead
  of just a scrolling status log - it's fed by the same progress_callback
  hook in card_pipeline.build_card_data, just mapped to a percentage.
- Visual polish: a filled red "hero" band for the title (matches the
  BearingPoint card design), and each question section is wrapped in a
  bordered card-style container (st.container(border=True)) instead of
  floating loosely on the page - reads as distinct, professional panels.

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

# --------------------------------------------------------------------------
# BearingPoint-style theming. Swap BRAND_RED below if you tweak the color
# in card_pipeline.py, so the app and the printed cards stay in sync.
# --------------------------------------------------------------------------
BRAND_RED = "#C8102E"

st.markdown(
    f"""
    <style>
    .stApp {{
        background: linear-gradient(180deg, #FFFFFF 0%, #FBEEF0 100%);
    }}
    h1, h2, h3 {{
        color: {BRAND_RED};
    }}
    div.stButton > button, div.stFormSubmitButton > button {{
        background-color: {BRAND_RED};
        color: white;
        border: none;
        border-radius: 999px;
        padding: 0.6em 1.6em;
        font-weight: 600;
    }}
    div.stButton > button:hover, div.stFormSubmitButton > button:hover {{
        background-color: #9c0c22;
        color: white;
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
    st.caption("💡 Add your logo at assets/logo.png to have it appear above the title.")

st.markdown(
    f"""
    <div style="background:{BRAND_RED}; padding:2em 1.5em; border-radius:20px;
                text-align:center; margin-bottom:1.5em;
                box-shadow:0 10px 28px rgba(200,16,46,0.28);">
        <h1 style="color:white; margin:0; font-size:2.1em;">✨ Create your Data Avatar Card</h1>
        <p style="color:white; opacity:0.92; margin-top:0.6em; margin-bottom:0; font-size:1.05em;">
            A minute of fun questions, then watch your data creature come to life.<br>No photo needed.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Generic agreement scale - deliberately doesn't reveal any archetype name,
# so the result is a surprise on the finished card, not something you pick
# yourself from the slider.
AGREEMENT_LABELS = {1: "Not me at all", 2: "A little bit", 3: "Somewhat", 4: "Pretty much", 5: "100% me"}


def agreement_slider(label: str, key: str) -> int:
    return st.select_slider(label, options=[1, 2, 3, 4, 5], value=3, format_func=lambda v: AGREEMENT_LABELS[v], key=key)


# The type_ question is a themed scenario instead of an abstract agreement
# scale, since "which data domain are you" is categorical, not one linear
# axis - each option reads as a natural reaction that maps to one domain,
# without ever naming the archetype/domain directly.
TYPE_SCENARIO_OPTIONS = [
    "Panic slightly, then Google \"what is a pipeline\"",
    "Quietly patch it before anyone even notices",
    "Make sure everything gets logged, labeled, and properly filed away",
    "Start digging for the pattern hiding behind the mess",
    "Get weirdly excited - this is a great case study for a model",
    "Ask the newest AI tool to just fix it for you",
]


with st.form("questionnaire"):
    first_name = st.text_input("First name")

    with st.container(border=True):
        st.subheader("How much is this... you?")
        st.caption("Rate each statement - your data persona gets revealed on the card afterwards 👀")

        evolution = agreement_slider("I've basically seen every kind of data disaster there is.", "evolution")
        st.markdown("**It's 5pm on a Friday and the data just broke. What's your first move?**")
        type_choice = st.radio(
            "type_scenario", TYPE_SCENARIO_OPTIONS, key="type_", label_visibility="collapsed",
        )
        type_ = TYPE_SCENARIO_OPTIONS.index(type_choice) + 1
        hp = agreement_slider("Last-minute chaos and changing requirements don't really rattle me.", "hp")
        ability = agreement_slider("People randomly come find me when they're stuck on something data-related.", "ability")
        attack1 = agreement_slider("I ask a hundred questions before I touch a single row of data.", "attack1")
        attack_text = agreement_slider("I can laugh about the daily chaos of working with data.", "attack_text")
        attack2 = agreement_slider("I'd rather brainstorm it out loud with the team than solve it alone in silence.", "attack2")

    with st.container(border=True):
        st.subheader("Just for fun")
        st.caption("These don't affect your stats - they just shape what your avatar looks like.")

        color_pref = st.radio("Pick a color that feels like you", COLOR_PREF_OPTIONS, horizontal=True)
        animal_pref = st.radio("Pick a spirit animal for your avatar", ANIMAL_PREF_OPTIONS, horizontal=True)
        style_vibe = st.radio("Pick a vibe", STYLE_VIBE_OPTIONS, horizontal=True)

    use_ai = st.checkbox(
        "Use AI generation (name / avatar / skill text)",
        value=True,
        help="Untick to quickly test the layout using rule-based fallbacks and a solid placeholder avatar, without calling any API.",
    )

    submitted = st.form_submit_button("Generate my card ✨")

if submitted:
    if not first_name:
        st.error("Please fill in your first name.")
        st.stop()

    answers = QuestionnaireAnswers(
        first_name=first_name,
        evolution=evolution,
        type_=type_,
        hp=hp,
        ability=ability,
        attack1=attack1,
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
        back_path = compose_card_back(card)
        front_path = compose_card_front(card.rarity)

        progress_bar.progress(100)
        caption_ph.markdown(f"**✅ Card {card.card_number} ready!**")

    st.session_state["card"] = card
    st.session_state["front_path"] = front_path
    st.session_state["back_path"] = back_path
    st.balloons()

if "card" in st.session_state:
    card = st.session_state["card"]
    front_path = st.session_state["front_path"]
    back_path = st.session_state["back_path"]

    st.success(f"Card {card.card_number} generated — Rarity: {card.rarity}")

    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            st.image(str(front_path), caption="Front")
        with col2:
            st.image(str(back_path), caption="Back")

    with st.expander("Card details"):
        st.write(
            {
                "Name": card.pokemon_name,
                "Level": card.level_name,
                "XP": card.xp,
                "Capability": f"{card.capability} ({card.domain_tag})",
                "Signature skill": card.skill_name,
                "Skill text": card.skill_text,
                "Progress": f"{card.progress_stage}/5 ({card.progress_label})",
                "Rarity": card.rarity,
                "Card number": card.card_number,
            }
        )

    if st.button("🖨️ Print this card"):
        try:
            print_card(str(front_path), str(back_path))
            st.success("Sent to printer!")
        except RuntimeError as e:
            st.error(str(e))
