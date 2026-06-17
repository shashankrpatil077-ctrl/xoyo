import json
import redis
import re
from rapidfuzz import process, fuzz

class SemanticRouter:
    def __init__(self):
        self.rc = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        self.macros_key = "xoyo:autoskills"
        # Match threshold (0-100). 90 ensures we only trigger on high-confidence matches.
        self.threshold = 90

    def add_skill(self, intent_phrases: list[str], action: dict):
        """Registers a new skill/macro."""
        skills = self.get_all_skills()
        # Prevent duplicates
        for sk_id, sk_data in skills.items():
            if sk_data.get("action") == action:
                # Add new phrases to existing skill
                existing = set(sk_data.get("phrases", []))
                existing.update(intent_phrases)
                sk_data["phrases"] = list(existing)
                self.rc.hset(self.macros_key, sk_id, json.dumps(sk_data))
                return sk_id

        skill_id = f"skill_{len(skills) + 1}"
        data = {
            "phrases": intent_phrases,
            "action": action
        }
        self.rc.hset(self.macros_key, skill_id, json.dumps(data))
        return skill_id

    def get_all_skills(self):
        skills = self.rc.hgetall(self.macros_key)
        return {k: json.loads(v) for k, v in skills.items()}

    def match_intent(self, user_text: str):
        """
        Returns the action dict if matched, else None.
        Runs in < 1ms.
        """
        skills = self.get_all_skills()
        if not skills:
            return None

        # Build a flat list of all phrases to match against
        all_phrases = []
        phrase_to_skill = {}
        for skill_id, skill_data in skills.items():
            for phrase in skill_data.get("phrases", []):
                all_phrases.append(phrase)
                phrase_to_skill[phrase] = skill_data.get("action")

        # Use rapidfuzz token_set_ratio: excellent for ignoring word order and slight variations.
        match = process.extractOne(user_text, all_phrases, scorer=fuzz.token_set_ratio)
        
        if match:
            matched_string, score, _ = match
            if score >= self.threshold:
                import re
                
                def clean_text(text):
                    return set(re.sub(r'[^\w\s]', ' ', text.replace('_', ' ').lower()).split())

                user_tokens = clean_text(user_text)
                matched_tokens = clean_text(matched_string)
                
                # Filler words that don't change the intent
                fillers = {"please", "can", "you", "could", "would", "kindly", "just", 
                           "for", "me", "right", "now", "hey", "hi", "hello", "xoyo", 
                           "a", "an", "the", "do", "i", "want", "to", "go", "ahead",
                           "ok", "okay", "thanks", "thank", "yes", "yeah", "yep", "sure",
                           "of", "is", "are", "am", "will", "shall", "lets", "let's",
                           "some", "at", "in", "my"}
                           
                extra_tokens = user_tokens - matched_tokens - fillers
                
                # If there are >1 extra meaningful words, it might be a complex command
                if len(extra_tokens) > 1:
                    return None
                
                # Mathematical negation and state-flip check
                state_flips = {
                    "on": "off", "off": "on",
                    "start": "stop", "stop": "start",
                    "open": "close", "close": "open",
                    "up": "down", "down": "up",
                    "enable": "disable", "disable": "enable",
                    "play": "pause", "pause": "play"
                }
                negations_single = {"dont", "never", "stop", "close", "kill", "not", "no", "without"}
                
                # Check for standard negations
                if user_tokens.intersection(negations_single) - matched_tokens.intersection(negations_single):
                    return None
                    
                # Check for state flips (if user has 'off' and match has 'on')
                for ut in user_tokens:
                    if ut in state_flips:
                        opposite = state_flips[ut]
                        if opposite in matched_tokens and ut not in matched_tokens:
                            return None
                            
                return phrase_to_skill[matched_string]
        
        return None

if __name__ == "__main__":
    router = SemanticRouter()
    print("SemanticRouter active.")
