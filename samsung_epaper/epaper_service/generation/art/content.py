"""
Content management for arrest headlines and stories.
"""
import random
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ArrestStory:
    """Data class for arrest stories."""
    headline: str
    story: str


class ContentManager:
    """Manages arrest headlines and stories."""
    
    def __init__(self):
        self._stories = self._load_default_stories()
    
    def _load_default_stories(self) -> list[ArrestStory]:
        """Load default arrest stories."""
        stories_data = [
            {
                "headline": "Local resident arrested for\naggressive bubble wrap popping",
                "story": "In a shocking turn of events, local resident was apprehended yesterday after neighbors complained about 'excessive and intimidating' bubble wrap popping that lasted for three consecutive hours. Witnesses report the suspect was 'popping with malicious intent' and refused to share the therapeutic packaging material with others. The suspect claimed they were 'just stressed' but authorities weren't buying it. Bail has been set at 500 unpopped bubbles."
            },
            {
                "headline": "Person detained for\npublic pineapple pizza consumption",
                "story": "Authorities responded to multiple distress calls reporting an individual brazenly consuming pineapple pizza in broad daylight. The suspect showed no remorse, even offering slices to horrified onlookers. Local Italian restaurant owners formed a protest outside the courthouse. The suspect's defense attorney plans to argue that 'taste is subjective,' but prosecutors remain confident. If convicted, they face up to 30 days of mandatory cooking classes."
            },
            {
                "headline": "Suspect caught red-handed\ntalking to plants inappropriately",
                "story": "Garden center security footage revealed the shocking behavior that led to yesterday's arrest. The suspect was caught whispering sweet nothings to succulents and making inappropriate comments to the ferns. 'You're looking particularly photosynthetic today' was among the recorded statements. Plant rights activists are calling for the maximum sentence. The accused maintains they were 'just being friendly' but the traumatized plants tell a different story."
            },
            {
                "headline": "Individual arrested for\nexcessive dad joke usage",
                "story": "After receiving over 47 complaints, police finally apprehended the serial dad joker who had been terrorizing the community with puns for months. Victims report being subjected to jokes so bad they caused 'physical pain and emotional distress.' The suspect's final joke before arrest: 'I guess this situation is really arresting.' Even the officers groaned. Rehabilitation programs are being considered."
            },
            {
                "headline": "BREAKING: Person caught\nsinging in shower too loudly",
                "story": "Neighbors finally had enough when the suspect's rendition of 'Bohemian Rhapsody' shattered three windows and scared local wildlife. The individual claimed they were 'just practicing for karaoke' but audio analysis revealed decibel levels comparable to a jet engine. The apartment building has started a support group for affected residents. Prosecutors are pushing for mandatory volume control training."
            },
            {
                "headline": "Suspect detained for\nreplying all to company emails",
                "story": "In what prosecutors are calling 'the most heinous abuse of email etiquette in recent memory,' the suspect replied-all to over 73 company-wide emails with responses ranging from 'LOL' to lengthy personal anecdotes. Coworkers reported inbox PTSD and productivity losses. The company's IT department is still recovering from the server strain. Digital etiquette classes have been mandated as part of the plea deal."
            },
            {
                "headline": "Local menace arrested for\nspoiling TV show endings",
                "story": "The suspect was finally caught after a three-month investigation into who was loudly discussing plot twists in public spaces. Victims reported having entire seasons ruined while waiting in coffee shop lines. The accused showed no remorse, stating 'it aired last night, that's plenty of time.' Prosecutors are seeking the maximum penalty: being forced to watch only reality TV for a year."
            },
            {
                "headline": "Person apprehended for\nmisusing grocery store express lane",
                "story": "Security footage clearly showed the suspect attempting to check out with 37 items in the '10 items or less' lane. When confronted, they argued that 'bananas count as one item regardless of quantity.' Other shoppers formed an angry mob demanding justice. The grocery store has since installed item-counting sensors. The suspect faces mandatory math tutoring as part of their sentence."
            }
        ]
        
        return [ArrestStory(**story) for story in stories_data]
    
    def get_random_story(self) -> ArrestStory:
        """Get a random arrest story."""
        return random.choice(self._stories)
    


def format_current_date() -> str:
    """Format the current date for tabloid display."""
    return datetime.now().strftime("%A, %B %d, %Y")


# Global content manager instance
import threading

_content_manager = None
_content_manager_lock = threading.Lock()

def get_content_manager() -> ContentManager:
    """Get the global content manager instance."""
    global _content_manager
    with _content_manager_lock:
        if _content_manager is None:
            _content_manager = ContentManager()
        return _content_manager