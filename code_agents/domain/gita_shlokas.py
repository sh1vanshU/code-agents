"""
Bhagavad Gita Shlokas — random verse for commit messages and agent wisdom.

Usage:
    from code_agents.domain.gita_shlokas import random_shloka
    shloka = random_shloka()  # returns dict with sanskrit, translation, reference
"""
from __future__ import annotations

import logging
import random

logger = logging.getLogger("code_agents.domain.gita_shlokas")

SHLOKAS = [
    {
        "sanskrit": "कर्मण्येवाधिकारस्ते मा फलेषु कदाचन ।",
        "hindi": "कर्म करने में ही तुम्हारा अधिकार है, फल में कभी नहीं।",
        "english": "Your right is to action alone, never to its fruits.",
        "ref": "2.47",
    },
    {
        "sanskrit": "योगः कर्मसु कौशलम् ।",
        "hindi": "कर्मों में कुशलता ही योग है।",
        "english": "Excellence in action is yoga.",
        "ref": "2.50",
    },
    {
        "sanskrit": "उद्धरेदात्मनात्मानं नात्मानमवसादयेत् ।",
        "hindi": "अपने आप को ऊपर उठाओ, अपने आप को गिराओ मत।",
        "english": "Elevate yourself by your own effort; do not degrade yourself.",
        "ref": "6.5",
    },
    {
        "sanskrit": "श्रद्धावान् लभते ज्ञानम् ।",
        "hindi": "श्रद्धावान व्यक्ति ज्ञान प्राप्त करता है।",
        "english": "The faithful one attains knowledge.",
        "ref": "4.39",
    },
    {
        "sanskrit": "नहि ज्ञानेन सदृशं पवित्रमिह विद्यते ।",
        "hindi": "इस संसार में ज्ञान के समान पवित्र कुछ भी नहीं है।",
        "english": "There is nothing as pure as knowledge in this world.",
        "ref": "4.38",
    },
    {
        "sanskrit": "सर्वधर्मान्परित्यज्य मामेकं शरणं व्रज ।",
        "hindi": "सभी धर्मों को त्यागकर मेरी शरण में आओ।",
        "english": "Abandon all paths and surrender to the supreme.",
        "ref": "18.66",
    },
    {
        "sanskrit": "यदा यदा हि धर्मस्य ग्लानिर्भवति भारत ।",
        "hindi": "जब-जब धर्म की हानि होती है, तब-तब मैं प्रकट होता हूँ।",
        "english": "Whenever there is decline of righteousness, I manifest myself.",
        "ref": "4.7",
    },
    {
        "sanskrit": "वासांसि जीर्णानि यथा विहाय नवानि गृह्णाति नरोऽपराणि ।",
        "hindi": "जैसे मनुष्य पुराने वस्त्र त्यागकर नये वस्त्र धारण करता है।",
        "english": "As a person puts on new garments, giving up old ones.",
        "ref": "2.22",
    },
    {
        "sanskrit": "मन एव मनुष्याणां कारणं बन्धमोक्षयोः ।",
        "hindi": "मन ही मनुष्य के बंधन और मोक्ष का कारण है।",
        "english": "The mind is the cause of bondage and liberation.",
        "ref": "6.5",
    },
    {
        "sanskrit": "अभ्यासेन तु कौन्तेय वैराग्येण च गृह्यते ।",
        "hindi": "अभ्यास और वैराग्य से मन को वश में किया जा सकता है।",
        "english": "Through practice and detachment, the mind can be controlled.",
        "ref": "6.35",
    },
    {
        "sanskrit": "क्रोधाद्भवति सम्मोहः सम्मोहात्स्मृतिविभ्रमः ।",
        "hindi": "क्रोध से मोह उत्पन्न होता है, मोह से स्मृति भ्रमित होती है।",
        "english": "From anger arises delusion; from delusion, loss of memory.",
        "ref": "2.63",
    },
    {
        "sanskrit": "ध्यायतो विषयान्पुंसः सङ्गस्तेषूपजायते ।",
        "hindi": "विषयों का चिंतन करने से उनमें आसक्ति उत्पन्न होती है।",
        "english": "Contemplating objects of the senses, attachment to them arises.",
        "ref": "2.62",
    },
    {
        "sanskrit": "समत्वं योग उच्यते ।",
        "hindi": "समत्व भाव को ही योग कहते हैं।",
        "english": "Equanimity of mind is called yoga.",
        "ref": "2.48",
    },
    {
        "sanskrit": "नैनं छिन्दन्ति शस्त्राणि नैनं दहति पावकः ।",
        "hindi": "इसे शस्त्र काट नहीं सकते, अग्नि जला नहीं सकती।",
        "english": "Weapons cannot cut it, fire cannot burn it.",
        "ref": "2.23",
    },
    {
        "sanskrit": "सुखदुःखे समे कृत्वा लाभालाभौ जयाजयौ ।",
        "hindi": "सुख-दुख, लाभ-हानि, जय-पराजय को समान मानकर कर्म करो।",
        "english": "Treating alike pleasure and pain, gain and loss, victory and defeat.",
        "ref": "2.38",
    },
    {
        "sanskrit": "ज्ञानं लब्ध्वा परां शान्तिमचिरेणाधिगच्छति ।",
        "hindi": "ज्ञान प्राप्त करके शीघ्र ही परम शांति को प्राप्त होता है।",
        "english": "Having gained knowledge, one soon attains supreme peace.",
        "ref": "4.39",
    },
    {
        "sanskrit": "श्रेयान्स्वधर्मो विगुणः परधर्मात्स्वनुष्ठितात् ।",
        "hindi": "अपना अपूर्ण धर्म भी दूसरे के पूर्ण धर्म से श्रेष्ठ है।",
        "english": "Better is one's own imperfect duty than another's duty well performed.",
        "ref": "3.35",
    },
    {
        "sanskrit": "संशयात्मा विनश्यति ।",
        "hindi": "संशय करने वाला नष्ट हो जाता है।",
        "english": "The doubter perishes.",
        "ref": "4.40",
    },
]


def random_shloka() -> dict:
    """Return a random Bhagavad Gita shloka."""
    return random.choice(SHLOKAS)


def format_shloka(shloka: dict = None) -> str:
    """Format a shloka for display or commit message."""
    if shloka is None:
        shloka = random_shloka()
    return (
        f"\n{shloka['sanskrit']}\n"
        f"({shloka['hindi']})\n"
        f"{shloka['english']}\n"
        f"— Bhagavad Gita {shloka['ref']}"
    )


def format_shloka_oneline(shloka: dict = None) -> str:
    """Format shloka as one line for commit messages."""
    if shloka is None:
        shloka = random_shloka()
    return f"{shloka['sanskrit']} — {shloka['english']} (Gita {shloka['ref']})"


# Rainbow ANSI colors for terminal display
_RAINBOW_COLORS = [
    "\033[1;31m",  # bright red
    "\033[1;33m",  # bright yellow
    "\033[1;32m",  # bright green
    "\033[1;36m",  # bright cyan
    "\033[1;34m",  # bright blue
    "\033[1;35m",  # bright magenta
    "\033[1;91m",  # light red
    "\033[1;93m",  # light yellow
    "\033[1;92m",  # light green
    "\033[1;96m",  # light cyan
]


def rainbow_text(text: str, bold: bool = False) -> str:
    """Color each word in a different rainbow color. Bold if specified."""
    import sys
    if not sys.stdout.isatty():
        return text
    words = text.split()
    colored = []
    b = "\033[1m" if bold else ""
    for i, word in enumerate(words):
        color = _RAINBOW_COLORS[i % len(_RAINBOW_COLORS)]
        colored.append(f"{b}{color}{word}\033[0m")
    return " ".join(colored)


def format_shloka_rainbow(shloka: dict = None) -> str:
    """Format shloka with rainbow colors — Sanskrit bold+large, English in matching colors."""
    if shloka is None:
        shloka = random_shloka()
    # Sanskrit: bold + rainbow (appears larger/prominent in terminal)
    sanskrit = rainbow_text(shloka["sanskrit"], bold=True)
    # English meaning: same rainbow colors (not dim grey)
    english_text = f"— {shloka['english']} (Gita {shloka['ref']})"
    english = rainbow_text(english_text)
    # Extra spacing for visual prominence
    return f"\n{sanskrit}\n{english}\n"
