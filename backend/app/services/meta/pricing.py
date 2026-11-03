"""Official Meta Model API list prices for *local estimates only*.

Source: https://dev.meta.ai/docs/pricing-rate-limits
These are not invoices.
"""

MUSE_SPARK_STANDARD = {
    "input_per_mtok": 1.25,
    "output_per_mtok": 4.25,
    "cached_input_per_mtok": 0.15,
}

SAM_VIDEO_PER_1K_FRAMES = 0.20
SAM_IMAGE_PER_1K = 2.50
SAM_MIN_VIDEO_FRAMES = 50
# Metering estimates only. These are never sent as token limits to the model.
# Omit max_completion_tokens and allow the model's native generation allowance.
WORKOUT_INPUT_TOKEN_ESTIMATE = 2500
WORKOUT_OUTPUT_TOKEN_ESTIMATE = 6000
WORKOUT_REASONING_EFFORT = "high"

COACHING_INPUT_TOKEN_ESTIMATE = 2000
COACHING_OUTPUT_TOKEN_ESTIMATE = 6000
COACHING_REASONING_EFFORT = "high"


def estimate_muse_cost(input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    billed_input = max(0, input_tokens - cached_tokens)
    return (
        billed_input / 1_000_000 * MUSE_SPARK_STANDARD["input_per_mtok"]
        + cached_tokens / 1_000_000 * MUSE_SPARK_STANDARD["cached_input_per_mtok"]
        + output_tokens / 1_000_000 * MUSE_SPARK_STANDARD["output_per_mtok"]
    )


def estimate_sam_video_cost(frames: int) -> float:
    billed = max(SAM_MIN_VIDEO_FRAMES, frames)
    return billed / 1000.0 * SAM_VIDEO_PER_1K_FRAMES


def estimate_sam_image_cost(images: int = 1) -> float:
    return images / 1000.0 * SAM_IMAGE_PER_1K
