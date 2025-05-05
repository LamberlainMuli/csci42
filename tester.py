from google import genai
from google.genai import types
from PIL import Image
from io import BytesIO
import logging
from django.conf import settings
from .models import UserOutfit
from user.models import UserProfile
from .image_generator import generate_outfit_image

logger = logging.getLogger(__name__)

IMAGE_GEN_MODEL_ALIAS = "gemini-2.0-flash-exp-image-generation"

def build_prompt(profile: UserProfile):
    """Compose prompt details using available profile data."""
    details = ["person wearing the outfit"]
    if profile.ethnicity_ai: details.append(f"{profile.ethnicity_ai}")
    if profile.height_cm: details.append(f"approx {profile.height_cm} cm tall")
    if profile.body_type_ai: details.append(f"{profile.body_type_ai} body type")
    if profile.weight_kg: details.append(f"approx {profile.weight_kg} kg")
    if profile.appearance_prompt_notes: details.append(profile.appearance_prompt_notes)
    if len(details) > 1:
        return " ".join(details) + "."
    else:
        return "person wearing the outfit."

def generate_outfit_image_with_critique(outfit: UserOutfit) -> tuple[Image.Image | None, str | None, str | None]:
    """
    Generates a composite image, sends to Gemini for critique and improved image separately.
    Returns: (generated_pil_image | None, critique_text | None, error_message | None)
    """
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        logger.error("GEMINI_API_KEY not configured.")
        return None, None, "AI service is not configured."

    # 1. Generate composite image
    try:
        composite_image_buffer = generate_outfit_image(outfit)
        if not composite_image_buffer:
            return None, None, "Failed to generate current outfit image."
        current_outfit_pil = Image.open(composite_image_buffer).convert("RGB")
    except Exception as e:
        logger.error(f"Error generating composite for {outfit.id}: {e}", exc_info=True)
        return None, None, "Error preparing current outfit image."

    # 2. Build user details
    try:
        profile = UserProfile.objects.get(user=outfit.user)
        user_details = build_prompt(profile)
    except UserProfile.DoesNotExist:
        logger.warning(f"Profile not found for {outfit.user.id}.")
        user_details = "person wearing the outfit."
    except Exception as e:
        logger.error(f"Error building prompt details: {e}")
        user_details = "person wearing the outfit."

    # 3. Set up client
    client = genai.Client(api_key=api_key)

    # 4. Generate critique
    critique_prompt = f"Analyze this outfit image (worn by: {user_details}). Provide a brief, friendly style critique (max 70 words) using Markdown formatting."
    logger.info(f"Critique prompt: {critique_prompt}")
    try:
        response_critique = client.models.generate_content(
            model=IMAGE_GEN_MODEL_ALIAS,
            contents=[critique_prompt, current_outfit_pil],
            config=types.GenerateContentConfig(response_modalities=['TEXT'])
        )
        if not response_critique.candidates:
            block_reason = response_critique.prompt_feedback.block_reason if response_critique.prompt_feedback else 'Unknown'
            logger.warning(f"Critique response blocked/empty for Outfit {outfit.id}. Reason: {block_reason}")
            critique_error = f"Critique generation blocked: {block_reason}"
            critique_text = None
        else:
            critique_text = None
            for part in response_critique.candidates[0].content.parts:
                if part.text:
                    critique_text = part.text.strip()
                    break
            if not critique_text:
                critique_error = "Critique response did not contain text."
            else:
                critique_error = None
    except Exception as e:
        logger.error(f"Error generating critique for Outfit {outfit.id}: {e}", exc_info=True)
        critique_error = f"Critique generation error: {str(e)[:100]}"
        critique_text = None

    # 5. Generate image
    image_gen_prompt = f"Based on the original outfit image provided, generate a single new, realistic, vertically oriented 512x768 image showing a more stylish and improved complete outfit suggestion inspired by the original items, suitable for a person described as: {user_details}. Ensure the generated image shows the full outfit clearly."
    logger.info(f"Image generation prompt: {image_gen_prompt}")
    print(f"Image generation prompt: {image_gen_prompt}")
    try:
        response_image = client.models.generate_content(
            model=IMAGE_GEN_MODEL_ALIAS,
            contents=[image_gen_prompt, current_outfit_pil],
            config=types.GenerateContentConfig(response_modalities=['TEXT', 'IMAGE'])
        )
        print(f"Image generation response: {response_image}")
        if not response_image.candidates:
            block_reason = response_image.prompt_feedback.block_reason if response_image.prompt_feedback else 'Unknown'
            logger.warning(f"Image generation response blocked/empty for Outfit {outfit.id}. Reason: {block_reason}")
            image_error = f"Image generation blocked: {block_reason}"
            generated_image_pil = None
        else:
            generated_image_pil = None
            for part in response_image.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith('image/'):
                    image_bytes = part.inline_data.data
                    generated_image_pil = Image.open(BytesIO(image_bytes))
                    break
            if not generated_image_pil:
                image_error = "Image generation response did not contain an image."
            else:
                image_error = None
    except Exception as e:
        logger.error(f"Error generating image for Outfit {outfit.id}: {e}", exc_info=True)
        image_error = f"Image generation error: {str(e)[:100]}"
        generated_image_pil = None

    # 6. Combine results
    if critique_error and image_error:
        error_message = f"{critique_error} | {image_error}"
        return None, None, error_message
    elif critique_error:
        return generated_image_pil, None, critique_error
    elif image_error:
        return None, critique_text, image_error
    else:
        return generated_image_pil, critique_text, None