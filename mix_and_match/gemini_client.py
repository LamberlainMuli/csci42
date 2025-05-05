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

    # 3. Retrieve item details for prompts
    items = outfit.items.select_related('product').all()
    item_details = []
    for item in items:
        product = item.product
        title = product.title
        description = product.description[:50] + '...' if product.description and len(product.description) > 50 else product.description or "No description"
        item_details.append(f"{title} - {description}")
    item_details_str = "; ".join(item_details) if item_details else "No items in the outfit."

    # 4. Set up client
    client = genai.Client(api_key=api_key)

    # 5. Generate critique
    critique_prompt = f'''
    You are a helpful and encouraging style assistant. Your goal is to provide constructive feedback on the outfit shown in the provided image. The outfit is worn by a person described as: {user_details}.

    The outfit consists of the following items: {item_details_str}

    Please analyze the outfit thoroughly and offer a friendly critique that helps the user understand its strengths and potential areas for refinement. Structure your feedback as follows:

    Overall Vibe & Strengths: Start with a positive observation. What works well in this outfit? What is the general style or feeling it conveys (e.g., relaxed, chic, sporty, professional)?

    Item Cohesion & Harmony:

    Style Consistency: Evaluate how well the different pieces work together in terms of formality and style category. Do they create a unified look, or do some items feel disconnected (e.g., a very formal top with very casual shorts)? Explain your reasoning.
    Color & Texture: Comment on the interplay of colors and textures. Do they complement each other? Is the combination visually interesting or potentially clashing?
    Fit, Balance & Proportions:

    Considering the items shown and the description ({user_details}), discuss the apparent fit and how the pieces balance each other proportionally. Does the silhouette seem harmonious? (For example, does a fitted top balance wider-leg pants well? Or does a very loose top paired with baggy bottoms create an overly voluminous look?)
    Occasion & Context Appropriateness:

    Suggest specific situations, events, or environments where this outfit would be a good fit. Be descriptive (e.g., "Perfect for running weekend errands," "A great choice for a casual dinner with friends," "Suitable for a creative workplace").
    Gently mention contexts where this outfit might be less ideal, providing a brief reason (e.g., "Might feel a bit too casual for a formal wedding," "Could be improved for a professional presentation by swapping the [item] for something more structured").
    Constructive Suggestions (Focus on Styling):

    Offer 1-2 actionable and gentle suggestions for how the existing items could be styled differently to enhance the look, if applicable. Focus on how to wear the pieces, not replacing them. Examples: "Consider tucking the shirt in for a more defined waistline," "Rolling the cuffs of the jeans could add a nice touch," "Experimenting with how the jacket is worn (open vs. closed) might change the feel." If the outfit already looks well-styled, acknowledge that.
    Important Guidelines for Your Response:

    Maintain a positive, encouraging, and friendly tone throughout.
    Be specific in your feedback, explaining why something works well or could be adjusted.
    Focus on providing constructive insights, not just criticism.
    Ensure suggestions respect the original items in the outfit.
    The aim is to empower the user with useful style insights about their chosen outfit."
    '''
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

    # 6. Generate image with retry logic
    image_gen_prompt = f'''
    Generate a single new, realistic, vertically oriented 512x768 image. Your sole purpose is to realistically visualize the exact clothing items provided in the original input image(s) as a complete outfit. This outfit should be depicted as worn by a person described as: {user_details}, presented against a neutral background.

    The outfit consists of the following items: {item_details_str}

    CRITICAL INSTRUCTIONS - Adherence is Mandatory:

    Exact Item Replication: You MUST replicate each clothing item precisely as it appears in its input image. This includes, but is not limited to:

    Exact Colors and Color Placement: Match all hues, shades, and where colors appear on the item.
    Specific Structural Details: Preserve all visible design elements like pleats, folds, ruffles, seams, pocket types and placement, collar shapes, button styles, integrated belts, specific tears or distressing, embroidery, and any other unique structural features. (For example, if the input shows a pleated skirt, the output MUST show a pleated skirt with similar pleating).
    Texture and Material Appearance: Maintain the visual texture shown in the input (e.g., denim, silk, knit, leather).
    Pattern Fidelity: Reproduce any patterns (stripes, florals, checks) accurately in scale, color, and placement.
    No Modifications or Additions:

    Do NOT alter the design of any item.
    Do NOT introduce new items, accessories, or garments not present in the input.
    Do NOT change the fundamental style category of the items.
    Contextualization:

    The complete outfit, composed only of the replicated items, should be shown worn by a person matching the {user_details} description.
    Ensure the full outfit is clearly visible and realistically lit.
    Objective Failure Condition: Any deviation from the specific visual appearance (color, structure, pattern, texture) of the items shown in the input images constitutes a failure to follow instructions. The output must look like the literal items from the input were assembled into an outfit."
    '''
    logger.info(f"Image generation prompt: {image_gen_prompt}")
    print(f"Image generation prompt: {image_gen_prompt}")
    
    generated_image_pil = None
    image_error = None
    max_attempts = 2  # Retry once with a simpler prompt if the first attempt fails

    for attempt in range(max_attempts):
        try:
            # Use simpler prompt on retry
            if attempt > 0:
                image_gen_prompt = (
                    f"Generate a realistic 512x768 vertical image of a stylish outfit for a person: {user_details}."
                )
                logger.info(f"Retry attempt {attempt + 1} with prompt: {image_gen_prompt}")
                print(f"Retry attempt {attempt + 1} with prompt: {image_gen_prompt}")

            response_image = client.models.generate_content(
                model=IMAGE_GEN_MODEL_ALIAS,
                contents=[image_gen_prompt, current_outfit_pil] if attempt == 0 else image_gen_prompt,
                config=types.GenerateContentConfig(response_modalities=['TEXT', 'IMAGE'])
            )
            logger.debug(f"Image response candidates: {response_image.candidates}")
            print(f"Image generation response: {response_image}")

            if not response_image.candidates:
                block_reason = response_image.prompt_feedback.block_reason if response_image.prompt_feedback else 'Unknown'
                logger.warning(f"Image generation response blocked/empty for Outfit {outfit.id}. Reason: {block_reason}")
                image_error = f"Image generation blocked: {block_reason}"
                continue

            generated_image_pil = None
            for part in response_image.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith('image/'):
                    image_bytes = part.inline_data.data
                    generated_image_pil = Image.open(BytesIO(image_bytes))
                    logger.info(f"Successfully generated image for Outfit {outfit.id}")
                    image_error = None
                    break
            if generated_image_pil:
                break  # Exit retry loop if image is generated
            else:
                image_error = "Image generation response did not contain an image."
                logger.warning(image_error)

        except Exception as e:
            logger.error(f"Error generating image for Outfit {outfit.id} (attempt {attempt + 1}): {e}", exc_info=True)
            image_error = f"Image generation error: {str(e)[:100]}"
            generated_image_pil = None

    # 7. Combine results
    if critique_error and image_error:
        error_message = f"{critique_error} | {image_error}"
        return None, None, error_message
    elif critique_error:
        return generated_image_pil, None, critique_error
    elif image_error:
        return None, critique_text, image_error
    else:
        return generated_image_pil, critique_text, None