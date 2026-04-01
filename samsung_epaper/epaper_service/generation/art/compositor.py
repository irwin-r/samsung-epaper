"""
Core tabloid generation functionality (compositor).
"""
import logging
from pathlib import Path

from PIL import Image, ImageDraw

from .config import TemplateConfig
from ..utils.fonts import resolve_font

logger = logging.getLogger(__name__)


class TabloidCompositorError(Exception):
    """Custom exception for tabloid compositor errors."""
    pass


class TabloidCompositor:
    """Generates tabloid layouts using templates and content."""

    def __init__(self):
        """Initialize the tabloid compositor."""
        pass
    
    def calculate_optimal_word_count(self, template: TemplateConfig) -> int:
        """
        Calculate optimal word count to fill the body text area.
        
        Args:
            template: Template configuration
            
        Returns:
            Estimated word count needed to fill the body area
        """
        bbox = template.body_bbox
        font_size = template.body_font.size
        
        # Improved estimates based on actual font metrics
        line_height = font_size + 3  # Same as used in _draw_body_text
        char_width_estimate = font_size * 0.5  # More accurate character width
        chars_per_line = bbox.width // char_width_estimate
        words_per_line = chars_per_line // 5.5  # Average word + space length
        max_lines = bbox.height // line_height
        
        # Calculate base capacity
        base_words = int(words_per_line * max_lines)
        
        # Target 150% of capacity to ensure we have plenty of text for clipping
        target_words = int(base_words * 1.5)
        
        logger.debug(f"Body area: {bbox.width}x{bbox.height}")
        logger.debug(f"Capacity: {base_words} words, targeting: {target_words} words")
        
        return max(200, target_words)  # Minimum 200 words
    
    def generate_tabloid(
        self,
        template: TemplateConfig,
        arrest_image_path: str,
        headline: str,
        story_text: str,
        date_text: str,
        output_path: str
    ) -> str:
        """
        Generate a tabloid layout using the provided template and content.
        
        Args:
            template: Template configuration
            arrest_image_path: Path to the arrest photo
            headline: Headline text
            story_text: Story body text
            date_text: Date text
            output_path: Where to save the generated tabloid

        Returns:
            Path to the generated tabloid
            
        Raises:
            TabloidCompositorError: If generation fails
        """
        try:
            logger.info(f"Generating tabloid using template {template.name}")

            # Load template image
            template_path = Path(template.image_path)
            if not template_path.exists():
                raise TabloidCompositorError(f"Template image not found: {template.image_path}")

            canvas = Image.open(template_path)
            draw = ImageDraw.Draw(canvas)
            
            # Load fonts
            headline_font = resolve_font(template.headline_font.name, template.headline_font.size)
            date_font = resolve_font(template.date_font.name, template.date_font.size)
            body_font = resolve_font(template.body_font.name, template.body_font.size)
            
            # Draw date
            self._draw_date(draw, template, date_text, date_font)
            
            # Draw headline
            self._draw_headline(draw, template, headline, headline_font)
            
            # Add arrest photo
            self._add_arrest_photo(canvas, template, arrest_image_path)

            # Draw body text
            self._draw_body_text(draw, template, story_text, body_font)

            # Save the tabloid
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(output_path)

            logger.info(f"Successfully generated tabloid: {output_path}")
            return str(output_path)

        except Exception as e:
            error_msg = f"Failed to generate tabloid: {e}"
            logger.error(error_msg)
            raise TabloidCompositorError(error_msg) from e
    
    def _draw_date(self, draw: ImageDraw.Draw, template: TemplateConfig, date_text: str, font):
        """Draw the date text with configurable alignment and formatting."""
        bbox = template.date_bbox
        config = template.date_font
        
        # Fill background if specified
        if config.background:
            draw.rectangle([
                bbox.x, bbox.y,
                bbox.x + bbox.width, bbox.y + bbox.height
            ], fill=config.background)
        
        # Handle different format types
        if getattr(config, 'format_type', 'single_line') == 'multi_line':
            self._draw_date_multi_line(draw, bbox, config, date_text, font)
        else:
            self._draw_date_single_line(draw, bbox, config, date_text, font)
    
    def _draw_date_single_line(self, draw: ImageDraw.Draw, bbox, config, date_text: str, font):
        """Draw date as single line with configurable alignment."""
        # Apply text transform if specified
        text_transform = getattr(config, 'text_transform', None)
        if text_transform == 'uppercase':
            date_text = date_text.upper()
        elif text_transform == 'lowercase':
            date_text = date_text.lower()
        
        # Truncate date text if too long
        max_width = bbox.width - 4  # 2px padding on each side
        while date_text and len(date_text) > 3:
            text_bbox = draw.textbbox((0, 0), date_text, font=font)
            if text_bbox[2] - text_bbox[0] <= max_width:
                break
            date_text = date_text[:-4] + "..."
        
        # Calculate position based on alignment
        text_bbox = draw.textbbox((0, 0), date_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = config.size
        
        # Vertical centering
        date_y = bbox.y + (bbox.height - text_height) // 2
        
        # Horizontal alignment
        alignment = getattr(config, 'alignment', 'left')
        if alignment == 'right':
            date_x = bbox.x + bbox.width - text_width - 2  # 2px right padding
        elif alignment == 'center':
            date_x = bbox.x + (bbox.width - text_width) // 2
        else:  # left
            date_x = bbox.x + 2  # 2px left padding
        
        draw.text((date_x, date_y), date_text, font=font, fill=config.color)
    
    def _draw_date_multi_line(self, draw: ImageDraw.Draw, bbox, config, date_text: str, font):
        """Draw date as multi-line format (DAY\\nMonth Date, Year)."""
        # Apply text transform if specified
        text_transform = getattr(config, 'text_transform', None)
        if text_transform == 'uppercase':
            date_text = date_text.upper()
        elif text_transform == 'lowercase':
            date_text = date_text.lower()
        
        try:
            # Parse the date text to create multi-line format
            # Handle format like "Friday, August 19, 2025"
            if ', ' in date_text:
                # Split by comma first
                parts = date_text.split(', ')
                if len(parts) >= 3:
                    day_name = parts[0]  # "Friday"
                    month_day = parts[1]  # "August 19"
                    year = parts[2]      # "2025"
                    
                    line1 = day_name
                    line2 = f"{month_day}, {year}"
                else:
                    # Fallback for unexpected comma format
                    line1 = parts[0] if parts else "TODAY"
                    line2 = ', '.join(parts[1:]) if len(parts) > 1 else date_text
            else:
                # Handle format like "Friday Aug 24 2018" (no commas)
                parts = date_text.split()
                if len(parts) >= 4:
                    day_name = parts[0]  # "Friday"
                    month = parts[1]     # "Aug"
                    day_num = parts[2]   # "24"
                    year = parts[3]      # "2018"
                    
                    line1 = day_name
                    line2 = f"{month} {day_num}, {year}"
                else:
                    # Fallback for unexpected format
                    line1 = date_text[:len(date_text)//2]
                    line2 = date_text[len(date_text)//2:]
        except Exception:
            # Final fallback
            line1 = "TODAY"
            line2 = date_text
        
        lines = [line1, line2]
        line_spacing = getattr(config, 'line_spacing', 2)  # Get configurable line spacing
        line_height = config.size + line_spacing
        total_height = len(lines) * line_height - line_spacing  # Remove last spacing
        
        # Vertical positioning (center the block)
        start_y = bbox.y + (bbox.height - total_height) // 2
        
        # Draw each line
        alignment = getattr(config, 'alignment', 'left')
        for i, line in enumerate(lines):
            text_bbox = draw.textbbox((0, 0), line, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            
            # Horizontal alignment
            if alignment == 'right':
                text_x = bbox.x + bbox.width - text_width - 2  # 2px right padding
            elif alignment == 'center':
                text_x = bbox.x + (bbox.width - text_width) // 2
            else:  # left
                text_x = bbox.x + 2  # 2px left padding
            
            text_y = start_y + i * line_height
            draw.text((text_x, text_y), line, font=font, fill=config.color)
    
    def _draw_headline(self, draw: ImageDraw.Draw, template: TemplateConfig, headline: str, font):
        """Draw the headline text."""
        bbox = template.headline_bbox
        config = template.headline_font
        
        # Fill background if specified
        if config.background:
            draw.rectangle([
                bbox.x, bbox.y,
                bbox.x + bbox.width, bbox.y + bbox.height
            ], fill=config.background)
        
        # Try to fit text with font size adjustment
        current_font_size = config.size
        min_font_size = max(8, config.size // 3)  # Don't go below 8pt or 1/3 original size
        headline_lines = []
        
        while current_font_size >= min_font_size:
            # Create font with current size
            current_font = resolve_font(config.name, current_font_size)
            
            # Word wrap headline
            headline_words = headline.replace('\\n', ' ').split()
            headline_lines = []
            current_line = []
            max_width = bbox.width - 10  # 5px padding on each side
            
            for word in headline_words:
                test_line = ' '.join(current_line + [word])
                text_bbox = draw.textbbox((0, 0), test_line, font=current_font)
                if text_bbox[2] - text_bbox[0] <= max_width:
                    current_line.append(word)
                else:
                    if current_line:
                        headline_lines.append(' '.join(current_line))
                        current_line = [word]
                    else:
                        headline_lines.append(word)
                        current_line = []
            
            if current_line:
                headline_lines.append(' '.join(current_line))
            
            # Check if all lines fit vertically
            if headline_lines:
                sample_bbox = draw.textbbox((0, 0), headline_lines[0], font=current_font)
                actual_line_height = sample_bbox[3] - sample_bbox[1]
                line_spacing = 3  # Reduced from 5 for better fit
                total_text_height = len(headline_lines) * actual_line_height + (len(headline_lines) - 1) * line_spacing
                
                if total_text_height <= bbox.height:
                    # Text fits! Use this font size
                    font = current_font
                    break
            
            # Reduce font size and try again
            current_font_size -= 2
        
        # Draw the headline with the final font
        if headline_lines:
            sample_bbox = draw.textbbox((0, 0), headline_lines[0], font=font)
            actual_line_height = sample_bbox[3] - sample_bbox[1]
            line_spacing = 3
            total_text_height = len(headline_lines) * actual_line_height + (len(headline_lines) - 1) * line_spacing
            
            # Center vertically in the bbox
            vertical_offset = (bbox.height - total_text_height) // 2
            start_y = bbox.y + vertical_offset
            headline_x = bbox.x + bbox.width // 2
            
            for i, line in enumerate(headline_lines):
                current_y = start_y + i * (actual_line_height + line_spacing) + actual_line_height // 2
                draw.text((headline_x, current_y), line, font=font,
                         fill=config.color, anchor='mm')
    
    def _add_arrest_photo(self, canvas: Image.Image, template: TemplateConfig, image_path: str):
        """Add the arrest photo to the tabloid layout."""
        bbox = template.arrest_photo_bbox
        
        if not Path(image_path).exists():
            logger.warning(f"Arrest image not found: {image_path}")
            return
        
        arrest_img = Image.open(image_path)
        
        # Resize to fill the entire bbox (crop overflow)
        target_width = bbox.width
        target_height = bbox.height
        
        # Calculate scale factors
        scale_width = target_width / arrest_img.width
        scale_height = target_height / arrest_img.height
        scale_factor = max(scale_width, scale_height)
        
        new_width = int(arrest_img.width * scale_factor)
        new_height = int(arrest_img.height * scale_factor)
        
        logger.debug(f"Resizing arrest photo: {new_width}x{new_height} (scale: {scale_factor:.2f})")
        arrest_img = arrest_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Crop to exact bbox size if needed
        if new_width > target_width or new_height > target_height:
            crop_left = max(0, (new_width - target_width) // 2)
            crop_top = 0  # Start crop from top instead of center
            crop_right = crop_left + target_width
            crop_bottom = crop_top + target_height
            
            arrest_img = arrest_img.crop((crop_left, crop_top, crop_right, crop_bottom))
            logger.debug(f"Cropped to exact size: {arrest_img.width}x{arrest_img.height}")
        
        # Paste at bbox location
        canvas.paste(arrest_img, (bbox.x, bbox.y))
    
    def _draw_body_text(self, draw: ImageDraw.Draw, template: TemplateConfig, story_text: str, font):
        """Draw the body text."""
        bbox = template.body_bbox
        config = template.body_font
        
        # Fill background if specified
        if config.background:
            draw.rectangle([
                bbox.x, bbox.y,
                bbox.x + bbox.width, bbox.y + bbox.height
            ], fill=config.background)
        
        # Word wrap the story text
        max_width = bbox.width
        words = story_text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            text_bbox = draw.textbbox((0, 0), test_line, font=font)
            if text_bbox[2] - text_bbox[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
                    current_line = []
        
        if current_line:
            lines.append(' '.join(current_line))
        
        # Calculate how many lines fit
        line_height = config.size + 3
        max_lines = bbox.height // line_height
        lines = lines[:max_lines]
        
        # Draw text from top (no vertical centering)
        start_y = bbox.y
        for i, line in enumerate(lines):
            text_y = start_y + i * line_height
            draw.text((bbox.x, text_y), line, font=font, fill=config.color)


def create_tabloid_compositor() -> TabloidCompositor:
    """Factory function to create a tabloid compositor."""
    return TabloidCompositor()