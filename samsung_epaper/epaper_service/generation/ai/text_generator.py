"""
AI text generation using OpenAI's API for headlines and body content.
"""
import logging
import os
from dataclasses import dataclass
from typing import Optional

try:
    import openai
    from dotenv import load_dotenv
    load_dotenv()
except ImportError as e:
    raise ImportError("Required packages not installed. Run: pip install openai python-dotenv") from e

logger = logging.getLogger(__name__)


@dataclass
class NewsStory:
    """Data class for generated news story."""
    headline: str
    body: str
    image_prompt: str


class TextGenerationError(Exception):
    """Custom exception for text generation errors."""
    pass


class OpenAITextGenerator:
    """Generates tabloid headlines and body text using OpenAI's API."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the text generator.
        
        Args:
            api_key: OpenAI API key. If None, will try to get from environment.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise TextGenerationError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                "or pass it directly to the constructor."
            )
        
        self.client = openai.OpenAI(api_key=self.api_key, max_retries=3)
    
    def generate_arrest_story(self, word_count_target: int = 200, gender_info: Optional[dict] = None) -> NewsStory:
        """
        Generate a humorous arrest headline and story.
        
        Args:
            word_count_target: Target word count for the body text
            gender_info: Optional gender information from local AI detection
            
        Returns:
            NewsStory with headline and body text
            
        Raises:
            TextGenerationError: If generation fails
        """
        logger.info(f"Generating arrest story with target: {word_count_target} words (aiming for {int(word_count_target * 1.2)}+ words)")
        
        try:
            prompt = self._create_story_prompt(word_count_target, gender_info)
            
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a creative writer specializing in humorous, absurd news stories. Write fake arrest stories that are clearly satirical and meant for entertainment."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=0.9,
                max_tokens=800
            )
            
            content = response.choices[0].message.content.strip()
            return self._parse_story_response(content)
            
        except Exception as e:
            error_msg = f"Failed to generate arrest story: {e}"
            logger.error(error_msg)
            raise TextGenerationError(error_msg) from e
    
    def _create_story_prompt(self, word_count_target: int, gender_info: Optional[dict] = None) -> str:
        """Create the prompt for story generation."""
        gender_context = ""
        if gender_info and gender_info.get('gender') != 'unknown':
            gender = gender_info['gender']
            confidence = gender_info.get('confidence', 0.0)
            if confidence > 0.5:
                gender_context = f"\n- The person in the photo appears to be {gender} (use appropriate pronouns and context)"
        
        return f"""Generate a humorous, absurd fake arrest story for entertainment purposes. The story should be clearly satirical and ridiculous.

Requirements:
- Create a funny headline (2 lines max, suitable for tabloid)
- Write a body story of approximately {word_count_target} words
- Generate an image prompt that incorporates the story theme while retaining the original subject{gender_context}
- AVOID religious, political, or sensitive content
- Be creative and unexpected with harmless absurd scenarios

Format your response exactly like this:

HEADLINE:
[Your 1-2 line headline here - do not use quotation marks]

BODY:
[IMPORTANT: Write AT LEAST {word_count_target} words - aim for {int(word_count_target * 1.2)} words or more. This story needs to fill a tabloid column completely. Write multiple detailed paragraphs with:
- Opening paragraph describing the arrest and charges
- Quotes from arresting officers with detailed descriptions
- Witness statements with specific details and reactions  
- Legal proceedings with absurd courtroom drama
- Background information about the "crime spree"
- Expert opinions from ridiculous specialists
- Community reactions and consequences
- Bail amount and sentencing details
Make it feel like a real investigative news story but completely absurd. More text is better - the system will trim if needed.]

IMAGE_PROMPT:
[Generate a structured image prompt using this exact format: "Transform this person into [scenario description]. Keep their original clothes, hairstyle, and appearance. [Add 1-2 crime-specific visual elements]. Use photorealistic style, bright lighting, tabloid-quality image." Choose one scenario: arrest mugshot with police station background, being caught in the act, courthouse steps, or police escort. Keep the prompt concise and professional.]

Make sure the body text is substantial enough to fill a tabloid column."""
    
    def _parse_story_response(self, content: str) -> NewsStory:
        """Parse the OpenAI response into headline, body, and image prompt."""
        try:
            lines = content.strip().split('\n')
            headline_section = []
            body_section = []
            image_prompt_section = []
            current_section = None
            
            for line in lines:
                line = line.strip()
                if line.upper().startswith('HEADLINE:'):
                    current_section = 'headline'
                    # Include any text after "HEADLINE:" on the same line
                    headline_text = line[9:].strip()
                    if headline_text:
                        headline_section.append(headline_text)
                elif line.upper().startswith('BODY:'):
                    current_section = 'body'
                    # Include any text after "BODY:" on the same line
                    body_text = line[5:].strip()
                    if body_text:
                        body_section.append(body_text)
                elif line.upper().startswith('IMAGE_PROMPT:'):
                    current_section = 'image_prompt'
                    # Include any text after "IMAGE_PROMPT:" on the same line
                    prompt_text = line[13:].strip()
                    if prompt_text:
                        image_prompt_section.append(prompt_text)
                elif line and current_section == 'headline':
                    headline_section.append(line)
                elif line and current_section == 'body':
                    body_section.append(line)
                elif line and current_section == 'image_prompt':
                    image_prompt_section.append(line)
            
            headline = ' '.join(headline_section).strip()
            body = ' '.join(body_section).strip()
            image_prompt = ' '.join(image_prompt_section).strip()
            
            if not headline or not body:
                raise TextGenerationError("Could not parse headline and body from response")
            
            # If image prompt is missing, fall back to default
            if not image_prompt:
                logger.warning("No image prompt found in response, using default")
                image_prompt = self._get_default_image_prompt()
            
            # Ensure headline fits tabloid format (add line break if needed)
            if len(headline) > 50 and '\n' not in headline:
                words = headline.split()
                mid_point = len(words) // 2
                headline = ' '.join(words[:mid_point]) + '\n' + ' '.join(words[mid_point:])
            
            logger.info(f"Generated story - Headline: {len(headline)} chars, Body: {len(body.split())} words, Image prompt: {len(image_prompt)} chars")
            
            return NewsStory(headline=headline, body=body, image_prompt=image_prompt)
            
        except Exception as e:
            logger.error(f"Failed to parse story response: {e}")
            logger.debug(f"Response content: {content}")
            raise TextGenerationError(f"Failed to parse story response: {e}") from e
    
    def _get_default_image_prompt(self) -> str:
        """Get default image prompt if none is generated."""
        return """Transform this person into a humorous arrest mugshot scene:
        - Add metal handcuffs on their wrists with hands in front at waist level
        - Place them against a police station height measurement wall background (with measurement lines showing 5'0", 5'6", 6'0", etc)
        - Give them a sheepish, embarrassed, or silly expression
        - Use bright police station lighting
        - Keep their original clothes, hairstyle, and appearance from the photo
        - Make it lighthearted and funny, not scary
        - Photorealistic style
        - Generate high quality image that will be resized for tabloid layout
        - Full body visible from knees up"""


def create_text_generator() -> OpenAITextGenerator:
    """Factory function to create a text generator."""
    return OpenAITextGenerator()