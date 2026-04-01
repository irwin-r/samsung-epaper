"""Art-domain prompt builders (provider-agnostic).

All prompts use IDENTITY_ANCHOR for face preservation and EPAPER_SUFFIX
for display optimization. These constants should be included in every
image generation prompt.
"""

IDENTITY_ANCHOR = (
    "Use the provided photo as the sole identity reference. Preserve the exact "
    "person's facial structure, eye shape and spacing, nose, mouth, jawline, "
    "cheekbones, eyebrows, age, skin tone, hairline, and any distinctive facial "
    "features or asymmetry (moles, freckles, facial hair, glasses). The person "
    "must be clearly recognizable as the same individual. Do not beautify, "
    "de-age, change ethnicity, or turn them into a generic model."
)

EPAPER_SUFFIX = (
    "Optimize for a 1440x2560 portrait colour ePaper display: vibrant saturated "
    "colours, strong contrast, crisp edges, rich detail readable from 2-3 meters. "
    "Use the full colour spectrum where appropriate — this is NOT a grayscale display. "
    "Portrait orientation, subject large in frame. One person only. "
    "No extra limbs, distorted hands, or duplicated features."
)


def get_arrest_prompt() -> str:
    """Get the default prompt for arrest photo generation."""
    return f"""{IDENTITY_ANCHOR}
Create a lighthearted parody police booking portrait. Show the person framed
from chest to head, centered against a police height-chart wall with measurement
marks. Keep their original everyday clothes, hairstyle, and accessories. The
subject holds a booking placard at chest level with a sheepish, mildly embarrassed
expression that feels playful rather than distressed. Bright direct flash lighting,
crisp documentary detail, realistic skin texture. Simple uncluttered background.
No officers, no violence, no grime, no injury — comedic parody tone only.
{EPAPER_SUFFIX}"""


def build_classical_prompt(style_prompt: str) -> str:
    """Pass through classical prompt — artwork prompts are already self-contained."""
    return style_prompt
