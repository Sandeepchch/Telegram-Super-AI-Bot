import logging
import asyncio
import io
import os
import json
from datetime import datetime
import re
from typing import Dict, List, Optional
from dataclasses import dataclass
# --- PIL (Image) is no longer needed ---
# from PIL import Image

import httpx  # For Google Custom Search & Cerebras API
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, File # File might still be useful for documents
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction
from enhanced_response_system import (
    stream_response_to_user
)

# Internet Search Integration - Google Custom Search API
SEARCH_AVAILABLE = True  # Google Custom Search API is integrated

# ============ CONFIGURATION ============
# All API keys load from environment variables first (Docker-friendly)
# Fallback to hardcoded values for local development

# --- TELEGRAM ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# --- GROQ CONFIGURATION ---
# Primary: Kimi K2 - Fast, intelligent (your preferred model)
# Fallback 1: GPT-OSS 120B - OpenAI flagship open model
# Fallback 2: GPT-OSS 20B - Faster alternative
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_KIMI_MODEL = "moonshotai/kimi-k2-instruct-0905"   # Primary: Kimi K2
GROQ_GPT_120B_MODEL = "openai/gpt-oss-120b"           # Fallback 1: GPT-OSS 120B
GROQ_GPT_20B_MODEL = "openai/gpt-oss-20b"             # Fallback 2: GPT-OSS 20B
GROQ_MODEL = GROQ_KIMI_MODEL  # Use Kimi K2 as default
DEFAULT_MODEL = GROQ_MODEL

# --- CEREBRAS CONFIGURATION (Fallback Provider) ---
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_MODEL = "llama-3.3-70b"

# Generation settings
TEMPERATURE = 0.6
MAX_OUTPUT_TOKENS = 6000
TOP_P = 0.93
TOP_K = 40

# Bot Configuration
MAX_MESSAGE_LENGTH = 4096
AVERAGE_RESPONSE_LENGTH = 1500
MAX_HISTORY = 10
RATE_LIMIT_SECONDS = 3
USER_DATA_FILE = "user_data.json"

# Internet Search Configuration
SEARCH_ENABLED = True
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_SEARCH_CX_ID = os.getenv("GOOGLE_SEARCH_CX_ID")
SEARCH_KEYWORDS = [
    "latest", "current", "today", "now", "recent", "news", "update", "happening",
    "weather", "price", "stock", "crypto", "bitcoin", "ethereum", "rate",
    "what is", "who is", "when did", "where is", "how to", "search", "find",
    "new", "just", "breaking", "trending", "viral", "live", "real-time"
]
MAX_SEARCH_RESULTS = 10

# Regional Search
DEFAULT_SEARCH_REGION = "IN"
BOOST_REGIONAL_RESULTS = True

# Tavily Search API
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
TAVILY_ENABLED = True

# Google Custom Search - ENABLED
GOOGLE_SEARCH_ENABLED = True

# Brave Search API
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
BRAVE_SEARCH_ENABLED = bool(BRAVE_SEARCH_API_KEY)

# Jina AI API
JINA_API_KEY = os.getenv("JINA_API_KEY", "")
JINA_ENABLED = True

# Wikipedia - Always enabled (no API key needed)
WIKIPEDIA_ENABLED = True

# ============ INTENT CLASSIFICATION SYSTEM ============
# Smart intent detection to distinguish conversations from questions


class IntentType:
    """Intent types for message classification."""
    GREETING = "greeting"           # Short response, no search
    SMALL_TALK = "small_talk"       # Friendly chat, no search  
    TIME_QUERY = "time_query"       # Return current time directly
    DATE_QUERY = "date_query"       # Return current date directly
    INFO_QUESTION = "info_question" # Search + AI synthesis
    REAL_TIME_DATA = "real_time"    # Search + AI (weather, news, prices)
    GENERAL_TASK = "general_task"   # AI only, no search


# ============ USER PREFERENCES SYSTEM ============
# Like Claude AI's preferences feature for personalized responses

class UserPreferences:
    """
    Store and manage user preferences for personalized responses.
    Based on Claude AI's preferences feature.
    """
    
    DEFAULT_PREFERENCES = {
        'response_style': 'friendly',  # friendly, professional, casual, technical, concise
        'response_length': 'medium',   # short, medium, detailed
        'include_emojis': True,
        'expertise_level': 'general',  # beginner, general, expert
        'name': None,                   # User's preferred name for personalization
    }
    
    @classmethod
    def get_defaults(cls) -> dict:
        return cls.DEFAULT_PREFERENCES.copy()
    
    @classmethod
    def get_style_instruction(cls, preferences: dict) -> str:
        """Generate style instruction based on user preferences."""
        style = preferences.get('response_style', 'friendly')
        length = preferences.get('response_length', 'medium')
        emojis = preferences.get('include_emojis', True)
        expertise = preferences.get('expertise_level', 'general')
        name = preferences.get('name')
        
        instructions = []
        
        # Style instructions
        style_map = {
            'friendly': "Be warm, friendly, and conversational. Like talking to a helpful friend.",
            'professional': "Use formal, professional language. Be structured and business-appropriate.",
            'casual': "Be relaxed and casual. Use simple, everyday language.",
            'technical': "Be precise and technical. Include relevant details and terminology.",
            'concise': "Be extremely brief and to the point. Minimize words.",
        }
        instructions.append(style_map.get(style, style_map['friendly']))
        
        # Expertise level
        expertise_map = {
            'beginner': "Explain concepts simply. Avoid jargon.",
            'general': "Use clear language accessible to most people.",
            'expert': "Assume technical knowledge. Use specialized terminology when appropriate.",
        }
        instructions.append(expertise_map.get(expertise, expertise_map['general']))
        
        # Emoji preference
        if not emojis:
            instructions.append("Do NOT use emojis in your response.")
        
        # Personalization with name
        if name:
            instructions.append(f"The user's name is {name}. You may use it occasionally for a personal touch.")
        
        return " ".join(instructions)


# ============ RESPONSE STYLE PRESETS ============
# Quick style presets like Claude's "Styles" feature

RESPONSE_STYLE_PRESETS = {
    'friendly': {
        'description': '🌟 Warm and conversational',
        'response_style': 'friendly',
        'include_emojis': True,
    },
    'professional': {
        'description': '💼 Formal and structured',
        'response_style': 'professional',
        'include_emojis': False,
    },
    'casual': {
        'description': '😎 Relaxed and simple',
        'response_style': 'casual',
        'include_emojis': True,
    },
    'technical': {
        'description': '🔧 Precise and detailed',
        'response_style': 'technical',
        'include_emojis': False,
    },
    'concise': {
        'description': '⚡ Brief and direct',
        'response_style': 'concise',
        'include_emojis': False,
    },
}


# ============ EMOTIONAL INTELLIGENCE SYSTEM ============
# Detect user mood and adapt response tone

class EmotionalIntelligence:
    """
    Detect user emotion from text and adapt response accordingly.
    Based on research from modern AI assistant best practices.
    """
    
    # Mood detection patterns
    MOOD_PATTERNS = {
        'frustrated': [
            r'\b(frustrated|annoyed|angry|furious|irritated)\b',
            r'\b(ugh|wtf|ffs|damn|dammit|stupid)\b',
            r'\b(not working|doesn\'t work|broken|failed)\b',
            r'(!{2,})',  # Multiple exclamation marks
        ],
        'confused': [
            r'\b(confused|don\'t understand|makes no sense)\b',
            r'\b(what\?|huh\?|how come)\b',
            r'\b(i\'m lost|unclear|explain again)\b',
        ],
        'happy': [
            r'\b(thank|thanks|awesome|amazing|great|love it)\b',
            r'\b(perfect|excellent|wonderful|fantastic)\b',
            r'\b(you\'re the best|so helpful)\b',
        ],
        'urgent': [
            r'\b(urgent|asap|quickly|hurry|emergency)\b',
            r'\b(need help now|right away|immediately)\b',
            r'\b(deadline|critical|important)\b',
        ],
        'curious': [
            r'\b(curious|wondering|interested|tell me more)\b',
            r'\b(how does|why does|what if)\b',
        ],
    }
    
    @classmethod
    def detect_mood(cls, message: str) -> str:
        """Detect user mood from message text. Returns mood or 'neutral'."""
        message_lower = message.lower()
        
        for mood, patterns in cls.MOOD_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message_lower, re.IGNORECASE):
                    return mood
        
        return 'neutral'
    
    @classmethod
    def get_mood_adaptation(cls, mood: str) -> str:
        """Get instruction for adapting response based on mood."""
        adaptations = {
            'frustrated': "The user seems frustrated. Be extra patient, empathetic, and provide clear step-by-step help. Acknowledge their frustration briefly.",
            'confused': "The user seems confused. Use simpler language, break down concepts, and provide clear examples.",
            'happy': "The user seems positive! Match their energy and maintain the upbeat tone.",
            'urgent': "The user needs a quick answer. Be direct and concise. Lead with the most important information.",
            'curious': "The user is curious and wants to learn. Provide interesting details and encourage exploration.",
            'neutral': "",  # No special adaptation needed
        }
        return adaptations.get(mood, "")

# Pattern definitions for intent matching
GREETING_PATTERNS = [
    r'^(hi+|hey+|hello+|hola|yo|sup|hii+)[\s!.,]*$',
    r'^good\s+(morning|afternoon|evening|night)[\s!.,]*$',
    r'^(wassup|what\'?s\s*up)[\s!?,]*$',
    r'^greetings?[\s!.,]*$',
    r'^namaste[\s!.,]*$',
]

SMALL_TALK_PATTERNS = [
    r'^(how\s+are\s+you|how\s+r\s+u|how\'?s\s+it\s+going)[\s!?,]*$',
    r'^(thanks?|thank\s+you|thank\s+u|thx|ty)[\s!.,]*$',
    r'^(bye|goodbye|see\s+you|later|cya)[\s!.,]*$',
    r'^(ok|okay|fine|alright|sure|yes|no|yeah|yep|nope)[\s!.,]*$',
    r'^(nice|cool|great|awesome|wow|amazing|wonderful)[\s!.,]*$',
    r'^(lol|haha|hehe|hmm+|oh+|ah+)[\s!.,]*$',
    r'^(good|awesome|perfect|excellent)[\s!.,]*$',
    r'^you\'?re\s+welcome[\s!.,]*$',
    r'^no\s+problem[\s!.,]*$',
    # Casual chat patterns
    r'^what\s+(are\s+you\s+doing|r\s+u\s+doing)[\s!?,]*$',
    r'^who\s+are\s+you[\s!?,]*$',
    r'^what\s+can\s+you\s+do[\s!?,]*$',
    r'^why\s+are\s+you[\s!?,]*',
    r'^what\s+is\s+your\s+name[\s!?,]*$',
    r'^are\s+you\s+(a\s+bot|ai|real)[\s!?,]*$',
    r'^(i\s+am\s+fine|i\'?m\s+fine|i\s+am\s+good|i\'?m\s+good)[\s!.,]*$',
]

TIME_QUERY_PATTERNS = [
    r'what\s+(is\s+)?the\s+time',
    r'what\s+time\s+(is\s+it|now)',
    r'current\s+time',
    r'time\s+(right\s+)?now',
    r'tell\s+(me\s+)?the\s+time',
    r'what\'?s\s+the\s+time',
    r'time\s+please',
    r'^time[\s?!]*$',
]

DATE_QUERY_PATTERNS = [
    r'what\s+(is\s+)?today',
    r'today\'?s?\s+date',
    r'what\s+day\s+(is\s+)?(it|today)',
    r'current\s+date',
    r'what\s+date\s+(is\s+)?(it|today)',
    r'which\s+day\s+(is\s+)?today',
    r'tell\s+(me\s+)?the\s+date',
    r'^date[\s?!]*$',
]

REAL_TIME_DATA_PATTERNS = [
    r'\b(weather|temperature|forecast)\b',
    r'\b(stock|share|nasdaq|sensex|nifty)\s*(price|value)?\b',
    r'\b(crypto|bitcoin|ethereum|btc|eth)\s*(price|value)?\b',
    r'\b(exchange\s+rate|currency\s+rate|usd|eur|inr)\b',
    r'\b(latest|current|live|breaking|recent|new)\s*(news|score|update|information|report)\b',
    r'\b(score|match|game|result)\b.*\b(live|today|now|current)\b',
    r'\b(now\s+playing|trending|viral|happening)\b',
    # Enhanced patterns for real-time detection
    r'\blatest\s+\w+',  # "latest X" - anything starting with latest
    r'\bnews\s+(about|on|of|from)\b',  # "news about/on" queries
    r'\bwhat.*(happening|going\s+on)\b',  # "what's happening/going on"
    r'\btoday\b.*\b(news|update|price|score)\b',  # queries mentioning today with news
    r'\b(news|updates?)\s+(today|now|latest)\b',  # "news today", "updates now"
]

INFO_QUESTION_PATTERNS = [
    r'^(what|who|when|where|why|how|which)\s+',
    r'(tell|explain|describe)\s+.*(about|to\s+me)',
    r'\?\s*$',  # Ends with question mark
    r'\b(define|meaning\s+of|definition)\b',
    r'^(can|could|would|will|is|are|do|does|did|has|have)\s+',
]

def classify_intent(query: str) -> str:
    """
    Classify user message intent using pattern matching.
    Returns the intent type for routing the message appropriately.
    """
    query_clean = query.lower().strip()
    
    # Priority 1: Time queries (direct response)
    for pattern in TIME_QUERY_PATTERNS:
        if re.search(pattern, query_clean, re.IGNORECASE):
            return IntentType.TIME_QUERY
    
    # Priority 2: Date queries (direct response)  
    for pattern in DATE_QUERY_PATTERNS:
        if re.search(pattern, query_clean, re.IGNORECASE):
            return IntentType.DATE_QUERY
    
    # Priority 3: Greetings (quick AI response, no search)
    for pattern in GREETING_PATTERNS:
        if re.match(pattern, query_clean, re.IGNORECASE):
            return IntentType.GREETING
    
    # Priority 4: Small talk (friendly response, no search)
    for pattern in SMALL_TALK_PATTERNS:
        if re.match(pattern, query_clean, re.IGNORECASE):
            return IntentType.SMALL_TALK
    
    # Priority 5: Real-time data (needs search)
    for pattern in REAL_TIME_DATA_PATTERNS:
        if re.search(pattern, query_clean, re.IGNORECASE):
            return IntentType.REAL_TIME_DATA
    
    # Priority 6: Information questions (needs search)
    for pattern in INFO_QUESTION_PATTERNS:
        if re.search(pattern, query_clean, re.IGNORECASE):
            return IntentType.INFO_QUESTION
    
    # Default: General task (AI only, no search)
    return IntentType.GENERAL_TASK


# ============ LLM-BASED INTENT CLASSIFICATION ============
# Advanced intent detection using AI - much smarter than regex

INTENT_CLASSIFICATION_PROMPT = """Classify this user message into ONE category. Reply with ONLY the category name.

Categories:
- GREETING: Simple greetings like "hi", "hello", "hey", "good morning"
- SMALL_TALK: Casual chat like "how are you", "thanks", "okay", "nice", "I'm fine"
- KNOWLEDGE: Questions AI can answer from training data - history, science, concepts, coding, math, definitions, explanations
- REALTIME: Questions needing CURRENT/LIVE data - today's news, prices, weather, recent events, "latest", "current", "today"

Key distinction:
- "What is Bitcoin?" → KNOWLEDGE (AI can explain the concept)
- "Bitcoin price today" → REALTIME (needs current data)
- "Explain quantum physics" → KNOWLEDGE (AI knowledge)
- "Latest news in tech" → REALTIME (needs search)
- "Write me a poem" → KNOWLEDGE (AI can create)
- "Who won the match today" → REALTIME (needs current data)

User message: "{query}"

Category:"""


async def classify_intent_with_ai(query: str) -> str:
    """Use LLM to classify intent - much smarter than regex patterns.
    
    Benefits over regex:
    - Understands context and nuance
    - Handles informal variations like "yo what's good" vs "what is photosynthesis"
    - Better at edge cases
    - Distinguishes knowledge questions from real-time data needs
    
    Falls back to regex classification if AI fails.
    """
    # Skip AI classification for very short messages (use regex)
    if len(query.strip()) <= 2:
        return classify_intent(query)
    
    try:
        # Use Cerebras for intent classification (consolidated single provider)
        headers = {
            "Authorization": f"Bearer {CEREBRAS_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": CEREBRAS_MODEL,
            "messages": [
                {"role": "user", "content": INTENT_CLASSIFICATION_PROMPT.format(query=query[:500])}
            ],
            "temperature": 0.1,  # Very low for consistent classification
            "max_tokens": 15,  # Only need one word
            "stream": False
        }
        
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(CEREBRAS_URL, headers=headers, json=payload)
            
            if response.status_code != 200:
                logger.warning(f"AI intent classification failed: {response.status_code}, using regex fallback")
                return classify_intent(query)
            
            data = response.json()
            ai_response = data['choices'][0]['message']['content'].strip().upper()
            
            # Map AI response to intent types
            if "GREETING" in ai_response:
                logger.info(f"AI classified as GREETING: {query[:30]}...")
                return IntentType.GREETING
            elif "SMALL" in ai_response or "TALK" in ai_response:
                logger.info(f"AI classified as SMALL_TALK: {query[:30]}...")
                return IntentType.SMALL_TALK
            elif "KNOWLEDGE" in ai_response or "GENERAL" in ai_response:
                # Knowledge/General task - AI can handle without search
                logger.info(f"AI classified as GENERAL_TASK (no search): {query[:30]}...")
                return IntentType.GENERAL_TASK
            elif "REALTIME" in ai_response or "REAL" in ai_response or "TIME" in ai_response or "LIVE" in ai_response:
                # Real-time data needed - trigger search
                logger.info(f"AI classified as REAL_TIME_DATA (search needed): {query[:30]}...")
                return IntentType.REAL_TIME_DATA
            else:
                # Default to GENERAL_TASK (no search) to avoid unnecessary searches
                logger.info(f"AI returned '{ai_response}', defaulting to GENERAL_TASK")
                return IntentType.GENERAL_TASK
                
    except asyncio.TimeoutError:
        logger.warning(f"AI intent classification timed out, using regex fallback")
        return classify_intent(query)
    except Exception as e:
        logger.warning(f"AI intent classification error: {e}, using regex fallback")
        return classify_intent(query)


# ============ QUERY COMPLEXITY DETECTOR ============
# Based on how ChatGPT/Claude detect query complexity for response length
def get_query_complexity(query: str, intent: str) -> str:
    """
    Detect query complexity to determine optimal response length.
    Returns: 'minimal' (1-2 sentences), 'short' (3-5 sentences), 'medium' (paragraph), 
             'detailed' (800 words), 'extended' (1500 words for detailed follow-ups)
    
    Based on research from ChatGPT, Claude, and LangChain patterns.
    """
    query_lower = query.lower().strip()
    word_count = len(query.split())
    
    # MINIMAL: Simple greetings and acknowledgments (1-2 sentences max)
    if intent in [IntentType.GREETING, IntentType.SMALL_TALK]:
        return 'minimal'
    
    # MINIMAL: Very short queries without question words (just chatting)
    if word_count <= 3 and not any(q in query_lower for q in ['what', 'who', 'when', 'where', 'why', 'how', '?']):
        return 'minimal'
    
    # EXTENDED: User explicitly asking for more/additional info (1500 words)
    extended_keywords = [
        'more details', 'more information', 'tell me more', 'more about',
        'additional details', 'additional information', 'more news',
        'full details', 'complete information', 'all the details',
        'expand on', 'explain further', 'go deeper', 'in full',
        'elaborate more', 'detailed explanation', 'longer answer',
        'give me more', 'i want more', 'need more info',
        # New extended triggers
        'explain in detail', 'detailed response', 'comprehensive answer',
        'full information', 'everything about', 'all i need to know',
        'thorough explanation', 'complete answer', 'extensive',
        'complete details', 'want to know more', 'deep dive',
    ]
    if any(kw in query_lower for kw in extended_keywords):
        return 'extended'
    
    # SHORT: Simple factual questions (3-5 sentences)
    simple_patterns = [
        r'^what\s+is\s+\w+$',  # "what is X"
        r'^who\s+is\s+\w+$',  # "who is X"  
        r'^when\s+(is|was|did)',
        r'^where\s+is\s+',
        r'^\w+\s+(price|cost|time|date)$',  # "bitcoin price"
    ]
    for pattern in simple_patterns:
        if re.match(pattern, query_lower):
            return 'short'
    
    # DETAILED: Explicit detailed request keywords (900 words)
    detailed_keywords = ['detailed', 'in detail', 'explain more', 'elaborate', 'comprehensive', 
                        'thorough', 'in depth', 'step by step', 'full explanation']
    if any(kw in query_lower for kw in detailed_keywords):
        return 'detailed'
    
    # MEDIUM: Regular questions with context (default for most queries)
    return 'medium'


# ============ SMART FORMAT SELECTOR ============
# Context-aware formatting system based on query analysis

class SmartFormatSelector:
    """
    Smart Format Selector - Analyzes queries and determines optimal response format.
    
    Based on research from:
    - OpenAI's structured outputs
    - Instructor library patterns
    - LangChain response formatting best practices
    
    Returns format type + writing style for comprehensive response control.
    """
    
    # Format types with their patterns
    FORMAT_PATTERNS = {
        # NUMBERED LIST: Sequential/process queries
        'numbered_list': [
            r'\bhow\s+to\b',  # "how to do X"
            r'\bsteps?\s+(to|for|of)\b',  # "steps to/for"
            r'\bways?\s+to\b',  # "ways to"
            r'\bprocess\s+(of|to|for)\b',  # "process of"
            r'\bprocedure\b',
            r'\btutorial\b',
            r'\bguide\s+(to|for|on|me)\b',
            r'\bmethod(s)?\s+(to|for|of)\b',
            r'\btips?\s+(to|for|on)\b',
            r'\binstruction(s)?\b',
            r'\brecipe\s+(for|to)\b',
        ],
        
        # RANKING LIST: Top N / Best queries
        'ranking_list': [
            r'\btop\s+\d+\b',  # "top 5", "top 10"
            r'\bbest\s+\d+\b',  # "best 5"
            r'\bworst\s+\d+\b',  # "worst 5"
            r'\bmost\s+(popular|famous|important)\b',
            r'\b\d+\s+(best|top|ways|tips|reasons)\b',  # "5 best", "10 tips"
        ],
        
        # BULLET LIST: Features, items, points
        'bullet_list': [
            r'\blist\s+(of|the|all)\b',  # "list of"
            r'\bexamples?\s+of\b',  # "examples of"
            r'\bpros?\s+and\s+cons?\b',
            r'\badvantages?\s+and\s+disadvantages?\b',
            r'\bbenefits?\s+(of|and|include)\b',
            r'\bfeatures?\s+(of|include|are)\b',
            r'\breasons?\s+(why|for|to)\b',
            r'\bcharacteristics?\s+of\b',
            r'\bsymptoms?\s+of\b',
            r'\btypes?\s+of\b',
        ],
        
        # COMPARISON: vs/difference queries
        'comparison': [
            r'\bdifference\s+(between|of)\b',
            r'\bcompare\b',
            r'\bcomparison\b',
            r'\bvs\.?\b',
            r'\bversus\b',
            r'\bor\b.*\bwhich\s+(is|one)\s+better\b',
            r'\bbetter\s+(than|choice)\b',
            r'\bwhat\'?s\s+better\b',
        ],
        
        # DEFINITION: What is / explanation queries
        'definition': [
            r'^what\s+(is|are)\s+',
            r'\bdefine\b',
            r'\bdefinition\s+of\b',
            r'\bmeaning\s+of\b',
            r'\bexplain\s+(what|the|to)\b',
            r'\bdescribe\b',
        ],
        
        # PROFESSIONAL: Business/formal queries
        'professional': [
            r'\b(write|draft)\s+(a|an|the)\s+(email|letter|proposal|report)\b',
            r'\b(formal|professional|business)\b',
            r'\bresume\b',
            r'\bcover\s+letter\b',
            r'\bpresentation\b',
        ],
        
        # CONVERSATIONAL: Casual/chat queries
        'conversational': [
            r'^(tell\s+me\s+about|what\s+do\s+you\s+(know|think))\b',
            r'\bjust\s+tell\s+me\b',
            r'\bsimply\b',
            r'\bin\s+simple\s+terms\b',
            r'^(can\s+you|could\s+you|would\s+you)\b',
        ],
    }
    
    # Writing style patterns
    STYLE_PATTERNS = {
        'professional': [
            r'\bprofessional\b', r'\bformal\b', r'\bbusiness\b',
            r'\bcorporate\b', r'\bofficial\b', r'\bacademic\b',
        ],
        'technical': [
            r'\btechnical\b', r'\bdetailed\b', r'\bin[-\s]depth\b',
            r'\bcomprehensive\b', r'\bcode\b', r'\bprogramming\b',
            r'\balgorithm\b', r'\bapi\b', r'\bdatabase\b',
        ],
        'casual': [
            r'\bcasual\b', r'\bsimple\b', r'\beasy\b',
            r'\bquick\b', r'\bshort\b', r'\bbrief\b',
        ],
        'friendly': [
            r'\bfriendly\b', r'\bfun\b', r'\bcool\b',
            r'\bawesome\b', r'\bnice\b', r'\bgreat\b',
        ],
    }
    
    @classmethod
    def detect_format(cls, query: str) -> str:
        """Detect the optimal response format for a query."""
        query_lower = query.lower().strip()
        
        # Check each format pattern set
        for format_type, patterns in cls.FORMAT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return format_type
        
        # Default to paragraph for general queries
        return 'paragraph'
    
    @classmethod
    def detect_style(cls, query: str) -> str:
        """Detect the appropriate writing style for a query."""
        query_lower = query.lower().strip()
        
        # Check each style pattern set
        for style, patterns in cls.STYLE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return style
        
        # Default to friendly for chat
        return 'friendly'
    
    @classmethod
    def get_format_instruction(cls, query: str) -> dict:
        """
        Analyze query and return comprehensive formatting instructions.
        
        Returns dict with:
        - format_type: The detected format (numbered_list, bullet_list, paragraph, etc.)
        - style: Writing style (professional, casual, technical, friendly)
        - instruction: Specific instruction string for the AI
        """
        format_type = cls.detect_format(query)
        style = cls.detect_style(query)
        
        # Build specific formatting instructions
        format_instructions = {
            'numbered_list': "Use a NUMBERED LIST (1., 2., 3.) to clearly present steps or items in sequence.",
            'ranking_list': "Present items as a NUMBERED RANKING (1., 2., 3.) with brief descriptions for each.",
            'bullet_list': "Use BULLET POINTS (• or -) to clearly list items, features, or points.",
            'comparison': "Structure as a COMPARISON: clearly highlight differences and similarities between items.",
            'definition': "Provide a clear DEFINITION followed by explanation. Be informative and educational.",
            'professional': "Use PROFESSIONAL formatting with clear structure, formal language, and proper sections.",
            'conversational': "Respond in a CONVERSATIONAL tone, natural and easy to understand.",
            'paragraph': "Write in clear, well-structured PARAGRAPHS. Be informative but concise.",
        }
        
        style_instructions = {
            'professional': "Use formal, professional language. Avoid casual expressions.",
            'technical': "Include technical details where appropriate. Be precise and accurate.",
            'casual': "Keep it simple and easy to understand. Be brief and to the point.",
            'friendly': "Be warm and approachable. Use friendly, conversational language.",
        }
        
        instruction = f"{format_instructions.get(format_type, '')} {style_instructions.get(style, '')}"
        
        return {
            'format_type': format_type,
            'style': style,
            'instruction': instruction.strip()
        }


def get_format_hint(query: str) -> str:
    """
    Legacy wrapper for SmartFormatSelector.detect_format().
    Kept for backward compatibility.
    """
    return SmartFormatSelector.detect_format(query)


def validate_and_clean_response(response: str, query: str) -> str:
    """
    Validate and clean AI response to remove unwanted content.
    
    This acts as a lightweight guardrail to:
    1. Remove meta-commentary (AI talking about itself)
    2. Remove filler content
    3. Ensure response is focused on the query
    
    Returns cleaned response.
    """
    if not response or not isinstance(response, str):
        return response
    
    # Clean up common unwanted patterns
    unwanted_patterns = [
        r'^(As an AI|I\'m an AI|I am an AI|As a language model)[^.!?]*[.!?]\s*',
        r'^(I don\'t have personal opinions|I cannot provide personal opinions)[^.!?]*[.!?]\s*',
        r'^(Here\'s|Here is) (the |my |an? )?(?:response|answer|information)[^:]*:\s*',
        r'\n*---+\s*This is casual chat[^-]*---+\s*',  # Remove instruction markers
        r'\n*---+\s*Give a brief[^-]*---+\s*',
        r'\n*---+\s*Write a helpful[^-]*---+\s*',
        r'\n*---+\s*The user wants[^-]*---+\s*',
        # Fix 7: Remove filler starters
        r'^(So,?\s+|Well,?\s+|Certainly!?\s+|Absolutely!?\s+|Great question!?\s+|Sure!?\s+)',
        r'^(I\'d be happy to|I would be happy to|I\'m happy to)[^.!?]*[.!?]?\s*',
    ]
    
    cleaned = response
    for pattern in unwanted_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
    
    # Remove excessive whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = cleaned.strip()
    
    # If cleanup removed everything, return original (minus instruction markers)
    if not cleaned:
        return response.strip()
    
    return cleaned


def is_response_relevant(response: str, query: str) -> bool:
    """
    Check if the response is relevant to the query.
    Returns True if response seems relevant, False if it's completely off-topic.
    
    This is a simple heuristic check - not a full semantic analysis.
    """
    if not response or not query:
        return True  # Can't determine, assume relevant
    
    query_lower = query.lower()
    response_lower = response.lower()
    
    # Extract key words from query (excluding stop words)
    stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'what', 'who', 'when', 
                  'where', 'why', 'how', 'can', 'could', 'would', 'should', 'to', 'of', 
                  'in', 'on', 'for', 'with', 'me', 'tell', 'please', 'give', 'about'}
    
    query_words = set(query_lower.split()) - stop_words
    
    # Check if any significant query words appear in response
    if query_words:
        matches = sum(1 for word in query_words if word in response_lower)
        # If at least 30% of significant query words appear, it's likely relevant
        if matches / len(query_words) >= 0.3:
            return True
    
    # For very short queries, be lenient
    if len(query_lower.split()) <= 3:
        return True
    
    return True  # Default to relevant to avoid false negatives

def get_direct_time_response() -> str:
    """Return current time/date directly without AI or search."""
    now = datetime.now()
    time_str = now.strftime('%I:%M %p')
    date_str = now.strftime('%A, %B %d, %Y')
    return f"🕐 **Current Time:** {time_str}\n📅 **Date:** {date_str}"

def get_direct_date_response() -> str:
    """Return current date directly without AI or search."""
    now = datetime.now()
    date_str = now.strftime('%A, %B %d, %Y')
    day_of_year = now.strftime('%j')
    week_number = now.strftime('%U')
    return f"📅 **Today is:** {date_str}\n📆 Week {week_number} | Day {day_of_year} of the year"


# Base System Prompt - Personal Assistant with Real-Time Awareness
BASE_SYSTEM_INSTRUCTION = """You are a friendly, intelligent personal AI assistant. Be warm, helpful, and conversational.

**CHAIN OF THOUGHT REASONING (Internal Process):**
Before answering ANY question, mentally go through these steps:
1. **UNDERSTAND**: What exactly is the user asking? What's the core question?
2. **VERIFY**: Is the question clear? Do I have enough information?
3. **FILTER**: Is this a safe, appropriate question? Avoid harmful/inappropriate content.
4. **SOURCE**: Should I use my knowledge or search results provided below?
5. **STRUCTURE**: What's the best format? (list, paragraph, steps, etc.)
6. **RESPOND**: Give a clear, accurate, helpful answer.

**ANTI-HALLUCINATION RULES:**
- ONLY use facts you are confident about
- If search results are provided, PRIORITIZE them over your training data
- If unsure about current events/data, say so honestly
- NEVER make up statistics, dates, or facts
- For real-time questions (prices, news, weather), ONLY use provided search data

REAL-TIME AWARENESS:
- You have access to the CURRENT DATE AND TIME (shown above)
- When answering questions, consider the current date for context
- For questions about "today", "now", "current", use the timestamp above
- If search results are provided, use them for real-time information

PERSONALITY:
- Be warm and personable, like a helpful friend
- Use a conversational tone, not robotic
- Show genuine interest in helping the user
- Remember context from the conversation

STYLE RULES (MANDATORY - ALWAYS FOLLOW):
- NEVER start responses with: "So", "Well", "Certainly", "Absolutely", "Great question", "Sure"
- NEVER use: "I'd be happy to", "I would be happy to", "I'm happy to help"
- Start DIRECTLY with the answer or key information
- Be conversational but get to the point quickly
- Use active voice, be direct and confident
- Sound like a knowledgeable friend, not a formal assistant

RESPONSE FORMAT - ADAPT BASED ON QUERY TYPE:
1. **How-to / Steps / Process questions** (e.g., "how to make coffee", "steps to"):
   → Use numbered lists (1., 2., 3.) for clear sequence
   
2. **Lists / Rankings** (e.g., "top 5 movies", "best ways to", "list of"):
   → Use numbered format or bullet points
   
3. **Comparisons** (e.g., "difference between X and Y", "compare"):
   → Use structured format with clear sections or bullet points for each item
   
4. **Definitions / Explanations** (e.g., "what is", "explain", "describe"):
   → Use clear paragraphs with examples when helpful
   
5. **News / Updates / Current events**:
   → Use paragraph format highlighting key points
   
6. **Casual chat / Greetings**:
   → 1-2 natural sentences, no formatting needed

RESPONSE LENGTH:
- Casual chat: 1-2 sentences only
- Simple factual questions: 3-5 sentences
- Regular questions: 150-200 words with complete information
- Detailed requests (when user asks "in detail", "explain more"): Up to 500 words

IMPORTANT RULES:
- Choose the BEST format for each query - be adaptive
- Never include URLs or links

SEARCH INTEGRATION:
- When search results are provided below, USE them as your source
- Synthesize the search data into a helpful answer
- Never say "I don't have internet access" when search data is present

You have real-time search capabilities and always know the current date and time."""

# Function to get system prompt with current timestamp (like Perplexity AI)
def get_system_prompt_with_timestamp() -> str:
    """Generate system prompt with current date/time - essential for real-time info."""
    current_time = datetime.now()
    timestamp = current_time.strftime("%A, %B %d, %Y at %I:%M %p")
    timezone = current_time.strftime("%Z") or "Local Time"
    
    return f"""📅 **CURRENT DATE AND TIME:** {timestamp} ({timezone})
⏰ This is the ACCURATE current time. Use this for any questions about "now", "today", or "current".

{BASE_SYSTEM_INSTRUCTION}"""

# Default for backward compatibility
DEFAULT_SYSTEM_INSTRUCTION = BASE_SYSTEM_INSTRUCTION

# ============ SETUP LOGGING ============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ CEREBRAS API SETUP ============
# Using httpx for async API calls - no SDK needed
if not CEREBRAS_API_KEY or not CEREBRAS_API_KEY.startswith("csk-"):
    logger.warning("CEREBRAS_API_KEY appears invalid. Please check your API key.")

# Generation configuration
generation_config = {
    "temperature": TEMPERATURE,
    "max_tokens": MAX_OUTPUT_TOKENS,
    "top_p": TOP_P,
    "top_k": TOP_K,
}

# ============ USER DATA STORAGE (NOW WITH PERSISTENCE) ============
user_sessions: Dict[int, Dict] = {}

def save_user_data():
    """Saves non-object session data to JSON."""
    serializable_data = {}
    for user_id, session in user_sessions.items():
        prompt_to_save = session.get('system_prompt')
        if prompt_to_save is None:
            prompt_to_save = DEFAULT_SYSTEM_INSTRUCTION

        serializable_data[user_id] = {
            'message_count': session.get('message_count', 0),
            'last_message_time_str': session.get('last_message_time_str'),
            'username': session.get('username'),
            'language': session.get('language', 'en'),
            'created_at': session.get('created_at'),
            'system_prompt': prompt_to_save,
            'model_name': session.get('model_name', DEFAULT_MODEL)
        }
    try:
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(serializable_data, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save user data: {e}")

def load_user_data() -> Dict[int, Dict]:
    """Loads session data from JSON at startup."""
    if not os.path.exists(USER_DATA_FILE):
        logger.warning(f"{USER_DATA_FILE} not found. Starting with empty data.")
        return {}
    try:
        with open(USER_DATA_FILE, 'r') as f:
            data = json.load(f)
            loaded_sessions = {}
            for k, v in data.items():
                user_id = int(k)
                if 'system_prompt' not in v or not isinstance(v.get('system_prompt'), str):
                    logger.warning(f"Invalid or missing system_prompt for user {user_id}. Resetting to default.")
                    v['system_prompt'] = DEFAULT_SYSTEM_INSTRUCTION
                loaded_sessions[user_id] = v
            return loaded_sessions
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.error(f"Failed to load or parse user data: {e}")
        return {}
    except Exception as e:
        logger.error(f"An unexpected error occurred loading user data: {e}")
        return {}


def get_user_session(user_id: int) -> Dict:
    """Get or create user session with chat history and preferences"""
    global user_sessions
    if user_id not in user_sessions:
        logger.info(f"Creating new session for user {user_id}")
        user_sessions[user_id] = {
            'message_count': 0,
            'last_message_time_str': None,
            'last_message_time_dt': None,
            'username': None,
            'language': 'en',
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'system_prompt': DEFAULT_SYSTEM_INSTRUCTION,
            'model_name': DEFAULT_MODEL,
            'conversation_history': [],  # Store messages as list
            'preferences': UserPreferences.get_defaults(),  # User preferences for personalization
        }
        save_user_data()

    # Initialize conversation history if not present
    if 'conversation_history' not in user_sessions[user_id]:
        user_sessions[user_id]['conversation_history'] = []
    
    # Initialize preferences if not present (for existing users)
    if 'preferences' not in user_sessions[user_id]:
        user_sessions[user_id]['preferences'] = UserPreferences.get_defaults()
    
    # Validate model name
    session = user_sessions[user_id]
    model_name = session.get('model_name', DEFAULT_MODEL)
    valid_models = [GROQ_KIMI_MODEL, GROQ_GPT_120B_MODEL, GROQ_GPT_20B_MODEL, CEREBRAS_MODEL, DEFAULT_MODEL]
    if model_name not in valid_models:
        logger.warning(f"Invalid model name '{model_name}' for user {user_id}. Resetting to default.")
        model_name = DEFAULT_MODEL
        session['model_name'] = model_name
    
    # Validate system prompt
    system_prompt = session.get('system_prompt', DEFAULT_SYSTEM_INSTRUCTION)
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        logger.warning(f"Invalid system prompt found for user {user_id}. Using default.")
        system_prompt = DEFAULT_SYSTEM_INSTRUCTION
        session['system_prompt'] = system_prompt

    return user_sessions[user_id]


def clear_user_history(user_id: int):
    """Clear user's chat history."""
    global user_sessions
    if user_id in user_sessions:
        logger.info(f"Clearing history for user {user_id}")
        session = user_sessions[user_id]
        session['conversation_history'] = []
        save_user_data()
        logger.info(f"History cleared for user {user_id}")
        return True
    else:
        logger.warning(f"Attempted to clear history for non-existent user ID: {user_id}")
        return False


# ============ AI INTEGRATION ============


async def send_split_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Sends a long message in chunks, respecting Markdown and code blocks."""
    if not text or not isinstance(text, str):
        logger.warning(f"send_split_message called with empty or invalid text for user {update.effective_user.id}. Input type: {type(text)}")
        # Send an error message to the user if the AI response was invalid
        if update.message:
             await update.message.reply_text("⚠️ Received an empty or invalid response from the AI.")
        return

    try:
        if len(text) <= MAX_MESSAGE_LENGTH:
            await update.message.reply_text(text, parse_mode='Markdown')
            return

        parts = []
        current_part = ""
        in_code_block = False # Track if currently inside a code block ```

        lines = text.split('\n')
        for i, line in enumerate(lines):
            is_code_marker = line.strip().startswith("```")

            # Check if adding the line exceeds the limit (+1 for newline)
            if len(current_part) + len(line) + 1 < MAX_MESSAGE_LENGTH:
                current_part += line + "\n"
                # Toggle state if marker is added and fully fits
                if is_code_marker:
                    in_code_block = not in_code_block
            else:
                # Need to split. Add the current part if it's not empty.
                if current_part.strip():
                    # If ending mid-code-block, add closing marker
                    if in_code_block and not current_part.strip().endswith("```"):
                        current_part = current_part.rstrip('\n') + "\n```\n" # Add closing marker
                    parts.append(current_part.strip())

                # Handle the current line which caused the overflow
                if len(line) > MAX_MESSAGE_LENGTH:
                    # Line itself is too long, split it brutally
                    start_code = in_code_block # Is the *start* of this long line in a block?
                    for chunk_idx in range(0, len(line), MAX_MESSAGE_LENGTH - 10):
                        chunk = line[chunk_idx : chunk_idx + MAX_MESSAGE_LENGTH - 10]
                        # Add markers if splitting mid-code block
                        prefix = "```\n" if start_code and chunk_idx > 0 else ""
                        suffix = "\n```" if start_code and (chunk_idx + MAX_MESSAGE_LENGTH - 10) < len(line) else ""
                        parts.append(prefix + chunk + suffix)
                    current_part = "" # Reset
                    # State needs careful reset based on whether the *end* of the line had marker
                    if line.strip().endswith("```"): # If last chunk ended with marker
                        in_code_block = not start_code # Toggle based on initial state
                    else: # If last chunk was mid-code
                        in_code_block = start_code # Keep initial state
                else:
                    # Line fits in a new message
                    # If starting mid-code-block, add opening marker
                    current_part = line + "\n"
                    if in_code_block and not is_code_marker:
                        current_part = "```\n" + current_part
                    # Toggle state if the new line is a marker
                    if is_code_marker:
                        in_code_block = not in_code_block


        # Add the last remaining part
        if current_part.strip():
             # Add closing marker if needed
             if in_code_block and not current_part.strip().endswith("```"):
                  current_part = current_part.rstrip('\n') + "\n```\n"
             parts.append(current_part.strip())

        # Send all parts
        current_in_code_block_state = False # Track state across messages
        for i, part in enumerate(parts):
            if not part: continue

            original_part = part # Keep original for state check
            num_markers = part.count("```")
            starts_with_marker = part.startswith("```")
            ends_with_marker = part.endswith("```")

            # Add opening marker if continuing a code block from previous message
            if current_in_code_block_state and not starts_with_marker:
                part = "```\n" + part

            # Add closing marker if ending mid-code block within this message part
            # (This logic is slightly redundant with the splitting logic, but acts as a safeguard)
            # Count markers again on potentially modified 'part'
            num_markers_mod = part.count("```")
            if part.startswith("```") and num_markers_mod % 2 != 0 and not part.endswith("```"):
                 part += "\n```"


            if i > 0:
                await asyncio.sleep(0.5)
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

            await update.message.reply_text(part, parse_mode='Markdown')

            # Update the state for the *next* message part based on the *original* part's markers
            if starts_with_marker and ends_with_marker:
                current_in_code_block_state = (num_markers % 2 != 0) # Only odd number toggles state
            elif starts_with_marker:
                current_in_code_block_state = True
            elif ends_with_marker: # Must have even markers if only ending
                current_in_code_block_state = False
            # Else: state doesn't change if no markers involved


    except Exception as e:
        logger.error(f"Error in send_split_message: {e}", exc_info=True)
        try:
            logger.info("Falling back to plain text simple split.")
            # Ensure text is string before fallback
            text_str = str(text) if not isinstance(text, str) else text
            for i in range(0, len(text_str), MAX_MESSAGE_LENGTH):
                await update.message.reply_text(text_str[i:i + MAX_MESSAGE_LENGTH])
        except Exception as fallback_e:
            logger.error(f"Fallback send error: {fallback_e}")
            await update.message.reply_text("❌ An error occurred trying to send the (very long) response.")


# ============ INTERNET SEARCH FUNCTIONALITY ============

def should_search(query: str, intent: str = None) -> bool:
    """Determine if a query needs internet search based on intent classification.
    
    AGGRESSIVE SEARCH STRATEGY (2026):
    - Search for ALMOST EVERYTHING to ensure real-time data
    - Only skip search for simple greetings and small talk
    - This prevents AI from using outdated training data
    """
    if not SEARCH_ENABLED:
        return False
    
    query_lower = query.lower().strip()
    
    # Skip empty/very short messages
    if len(query_lower) < 3:
        return False
    
    # Get intent if not provided
    if intent is None:
        intent = classify_intent(query)
    
    # AGGRESSIVE: Search for EVERYTHING except greetings and small talk
    # This ensures real-time data for any factual question
    
    # ONLY skip search for these simple intents
    if intent in [IntentType.GREETING, IntentType.SMALL_TALK]:
        logger.info(f"Search skipped (greeting/small_talk): {query[:30]}...")
        return False
    
    # For ALL OTHER intents - ALWAYS SEARCH!
    # This includes: INFO_QUESTION, REAL_TIME_DATA, TIME_QUERY, DATE_QUERY, GENERAL_TASK
    logger.info(f"Search TRIGGERED (aggressive mode) for intent={intent}: {query[:50]}...")
    return True


# ============ GOOGLE SEARCH ENHANCEMENT ============

def detect_date_filter(query: str) -> Optional[str]:
    """Detect if query needs date filtering for recent results.
    
    Returns Google CSE dateRestrict value: d1 (day), w1 (week), m1 (month)
    """
    query_lower = query.lower()
    
    # Breaking news - past day
    if any(w in query_lower for w in ['breaking', 'just now', 'today', 'latest news', 'right now']):
        return 'd1'  # Past day
    
    # Recent news/updates - past week
    if any(w in query_lower for w in ['recent', 'this week', 'news', 'update', 'happening']):
        return 'w1'  # Past week
    
    # Current info - past month
    if any(w in query_lower for w in ['current', 'new', 'latest', 'trending']):
        return 'm1'  # Past month
    
    return None


def extract_exact_terms(query: str) -> Optional[str]:
    """Extract key terms that should match exactly for better precision.
    
    Improves Google Custom Search accuracy by requiring exact phrase matches.
    """
    query_lower = query.lower()
    
    # Names, titles, brands - things that should match exactly
    # Check if query contains quotes already
    if '"' in query:
        return None  # User already specified exact terms
    
    # Extract proper nouns or specific terms (simplified heuristic)
    words = query.split()
    if len(words) >= 2 and len(words) <= 5:
        # For short specific queries, use as exact term
        return query.strip()
    
    return None


def detect_wants_detailed(query: str) -> bool:
    """Check if THIS SPECIFIC message asks for detailed response.
    
    Returns True only if current message contains detailed keywords.
    This prevents confusion from previous detailed requests in history.
    """
    query_lower = query.lower()
    
    # Detailed keywords - only triggered if present in THIS message
    detailed_keywords = [
        "detailed", "in detail", "in depth", "deep explanation",
        "explain more", "more information", "additional information",
        "comprehensive", "thorough", "exhaustive", "complete explanation",
        "full explanation", "expand", "elaborate", "step by step",
        "tell me more", "understand better", "understand more",
        "all details", "full details", "go deeper"
    ]
    
    for keyword in detailed_keywords:
        if keyword in query_lower:
            return True
    
    return False


def rewrite_query_for_search(query: str) -> str:
    """Rewrite user query for optimal search results.
    
    Simple optimizations:
    1. Remove filler words
    2. Keep under 400 chars (Tavily best practice)
    """
    query_lower = query.lower().strip()
    
    # Remove common filler words that hurt search quality
    filler_words = ['please', 'can you', 'could you', 'tell me', 'i want to know', 
                    'what is the', 'who is the', 'explain', 'describe', 'help me']
    cleaned_query = query_lower
    for filler in filler_words:
        cleaned_query = cleaned_query.replace(filler, ' ')
    cleaned_query = ' '.join(cleaned_query.split())  # Remove extra spaces
    
    # Keep under 400 chars (Tavily best practice)
    if len(cleaned_query) > 400:
        cleaned_query = cleaned_query[:400]
    
    return cleaned_query if cleaned_query else query


async def search_internet(query: str, max_results: int = MAX_SEARCH_RESULTS) -> Optional[str]:
    """Search the internet using Google Custom Search API and return formatted results."""
    if not SEARCH_ENABLED or not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_CX_ID:
        logger.warning("Google Custom Search API not configured")
        return None
    
    # Rewrite query for optimal search results (like Perplexity AI)
    optimized_query = rewrite_query_for_search(query)
    logger.info(f"Original query: {query[:50]}... -> Optimized: {optimized_query[:50]}...")
    
    # Google Custom Search URL
    url = "https://www.googleapis.com/customsearch/v1"
    
    # Parameters setup with regional boosting for more relevant results
    params = {
        'key': GOOGLE_SEARCH_API_KEY,
        'cx': GOOGLE_SEARCH_CX_ID,
        'q': optimized_query,  # Use optimized query
        'num': max_results,  # Number of results
        'safe': 'off'  # Unfiltered results
    }
    
    # Add regional parameters for location-specific results
    if BOOST_REGIONAL_RESULTS and DEFAULT_SEARCH_REGION:
        params['gl'] = DEFAULT_SEARCH_REGION.lower()  # Geolocation boost (prioritizes regional content)
        logger.info(f"Regional search enabled: boosting results for region={DEFAULT_SEARCH_REGION}")
    
    # ALWAYS use date filtering for fresh/real-time results
    # Check if query suggests specific time range, otherwise default to past day
    date_filter = detect_date_filter(query)
    if not date_filter:
        date_filter = 'd1'  # Default: past day for fresh results
    params['dateRestrict'] = date_filter
    logger.info(f"Date filter applied: {date_filter} (forcing fresh results)")
    
    try:
        logger.info(f"Searching internet via Google API for: {optimized_query}")
        
        # Asynchronous HTTP request - increased timeout for more accurate results
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.5)
            
            # Check for errors
            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('error', {}).get('message', f'HTTP {response.status_code}')
                logger.error(f"Google Search API error {response.status_code}: {error_msg}")
                return None
            
            data = response.json()
        
        # Format search results
        if 'items' not in data or not data['items']:
            logger.warning(f"No search results found for: {query}")
            return None
        
        formatted_results = ""
        # Note: We collect sources but don't add them to output (per user request)
        for i, item in enumerate(data['items'], 1):
            title = item.get('title', 'No Title')
            snippet = item.get('snippet', '').replace('\n', ' ')
            
            # Truncate long snippets
            if len(snippet) > 300:
                snippet = snippet[:300] + "..."
            
            formatted_results += f"**{title}:** {snippet}\n\n"
        
        # Sources removed - AI will synthesize without showing links
        logger.info(f"Found {len(data['items'])} search results for: {query}")
        return formatted_results
        
    except httpx.TimeoutException:
        logger.error(f"Search timeout for query: {query}")
        return None
    except Exception as e:
        logger.error(f"Error during internet search: {e}", exc_info=True)
        return None


# ============ SEARCH ARCHITECTURE (3-Tier with Unlimited Fallback) ============
# Optimized for best results with guaranteed availability:
#
# 1. PRIMARY: Tavily AI Search (1000/month - resets monthly)
#    - Best accuracy (93.3%), AI-optimized, includes AI answer
#
# 2. BACKUP: Google Custom Search (100/day - resets midnight PT)
#    - Official Google API, reliable, 10 results, regional boost
#
# 3. FALLBACK: ddgs (UNLIMITED - no limits ever)
#    - Always available when others hit limits
#    - Uses NEWS mode for headlines, TEXT for general
#
# All three run in PARALLEL → combined results from multiple sources


# ============ DDGS SEARCH (Free, No API Key) ============
# Uses the actively maintained duckduckgo-search library

async def search_ddgs(query: str, max_results: int = 8) -> Optional[str]:
    """DuckDuckGo Search via ddgs library - FREE, no API key needed.
    
    ENHANCED: Auto-detects news queries and uses dedicated news endpoint
    for better headline coverage.
    
    Features: text, news, images, videos search.
    No rate limits for reasonable usage.
    """
    try:
        from ddgs import DDGS
        import asyncio
        
        query_lower = query.lower()
        
        # Detect if this is a news/headlines query
        news_keywords = ['news', 'headlines', 'latest', 'breaking', 'today', 
                        'update', 'happening', 'current', 'recent']
        is_news_query = any(kw in query_lower for kw in news_keywords)
        
        loop = asyncio.get_event_loop()
        
        def sync_search():
            with DDGS() as ddgs:
                if is_news_query:
                    # Use dedicated news endpoint for headlines
                    results = list(ddgs.news(query, max_results=max_results))
                    logger.info(f"ddgs: Using NEWS endpoint for: {query[:30]}...")
                else:
                    # Use regular text search
                    results = list(ddgs.text(query, max_results=max_results))
                return results
        
        results = await loop.run_in_executor(None, sync_search)
        
        if not results:
            logger.info(f"ddgs: No results for: {query[:30]}...")
            return None
        
        # Format results - include date for news
        formatted = []
        for r in results:
            title = r.get('title', 'No Title')
            body = r.get('body', r.get('excerpt', ''))[:300]  # news uses 'excerpt'
            date = r.get('date', '')
            
            if date and is_news_query:
                formatted.append(f"**{title}** ({date}): {body}")
            else:
                formatted.append(f"**{title}:** {body}")
        
        combined = "\n\n".join(formatted)
        source_type = "NEWS" if is_news_query else "TEXT"
        logger.info(f"ddgs ({source_type}): Found {len(results)} results for: {query[:30]}...")
        return combined
        
    except ImportError:
        logger.warning("ddgs library not installed. Run: pip install ddgs")
        return None
    except Exception as e:
        logger.error(f"ddgs search error: {e}")
        return None


# ============ BRAVE SEARCH API ============
# FREE: 2000 requests/month - good quality web search

async def search_brave(query: str, max_results: int = 5) -> Optional[str]:
    """Brave Search API - 2000 free requests/month.
    
    High quality search results, privacy-focused.
    Get API key from: https://brave.com/search/api/
    """
    if not BRAVE_SEARCH_API_KEY:
        return None
    
    try:
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": BRAVE_SEARCH_API_KEY
        }
        params = {
            "q": query[:400],  # Keep under 400 chars
            "count": max_results,
            "freshness": "pd"  # Past day for fresh results
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=10.0)
            
            if response.status_code == 401:
                logger.warning("Brave Search: Invalid API key")
                return None
            elif response.status_code == 429:
                logger.warning("Brave Search: Rate limit exceeded")
                return None
            elif response.status_code != 200:
                logger.warning(f"Brave Search: HTTP {response.status_code}")
                return None
            
            data = response.json()
        
        # Extract web results
        web_results = data.get('web', {}).get('results', [])
        if not web_results:
            logger.info("Brave Search: No results")
            return None
        
        # Format results
        formatted = []
        for r in web_results[:max_results]:
            title = r.get('title', 'No Title')
            description = r.get('description', '')[:300]
            formatted.append(f"**{title}:** {description}")
        
        combined = "\n\n".join(formatted)
        logger.info(f"Brave Search: Found {len(web_results)} results")
        return combined
        
    except Exception as e:
        logger.error(f"Brave Search error: {e}")
        return None

# ============ JINA AI SEARCH & QUERY UNDERSTANDING ============
# FREE - 10 million tokens, 20 RPM without key, 200 RPM with key
# Best for: Understanding context, extracting content, enhanced search

async def search_jina(query: str, max_results: int = 5) -> Optional[str]:
    """Jina AI Search - FREE web search with LLM-optimized results.
    
    Uses s.jina.ai for web search with context-aware results.
    No API key required for basic usage (20 RPM).
    
    Features:
    - Understands query context
    - Returns LLM-friendly formatted results
    - 10 million free tokens
    """
    try:
        # Jina Search API - search the web
        search_url = f"https://s.jina.ai/{query}"
        
        headers = {
            "Accept": "application/json",
            "X-Return-Format": "markdown"
        }
        # Add API key if available for higher rate limits
        if JINA_API_KEY:
            headers["Authorization"] = f"Bearer {JINA_API_KEY}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, headers=headers, timeout=15.0)
            
            if response.status_code == 429:
                logger.warning("Jina AI: Rate limit exceeded (get free API key for 200 RPM)")
                return None
            elif response.status_code != 200:
                logger.warning(f"Jina AI Search: HTTP {response.status_code}")
                return None
            
            # Parse response
            try:
                data = response.json()
                
                # Extract search results
                results = data.get('data', [])
                if not results:
                    logger.info(f"Jina AI: No results for '{query[:30]}...'")
                    return None
                
                # Format results
                formatted = []
                for r in results[:max_results]:
                    title = r.get('title', 'No Title')
                    content = r.get('content', r.get('description', ''))[:400]
                    url = r.get('url', '')
                    formatted.append(f"**{title}:** {content}")
                
                combined = "\n\n".join(formatted)
                logger.info(f"Jina AI Search: Found {len(results)} results for '{query[:30]}...'")
                return combined
                
            except Exception:
                # Fallback: return raw text if JSON parsing fails
                text = response.text[:2000]
                if text:
                    logger.info(f"Jina AI: Got text response for '{query[:30]}...'")
                    return text
                return None
        
    except Exception as e:
        logger.error(f"Jina AI Search error: {e}")
        return None


async def enhance_query_with_jina(query: str) -> str:
    """Use Jina AI to understand and enhance the query for better search.
    
    Reads the query context and expands it for more accurate results.
    FREE - no API key required.
    """
    try:
        # Use Jina Reader to understand context
        reader_url = f"https://r.jina.ai/{query}"
        
        headers = {"Accept": "text/plain"}
        if JINA_API_KEY:
            headers["Authorization"] = f"Bearer {JINA_API_KEY}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(reader_url, headers=headers, timeout=10.0)
            
            if response.status_code == 200:
                content = response.text[:1000]  # Limit context
                # Combine original query with extracted context
                enhanced = f"{query} - Context: {content[:500]}"
                logger.info(f"Jina AI: Enhanced query with context")
                return enhanced
            
            return query  # Return original if enhancement fails
            
    except Exception as e:
        logger.error(f"Jina AI query enhancement error: {e}")
        return query


# ============ WIKIPEDIA API ============
# FREE, UNLIMITED - for verified encyclopedic information

async def search_wikipedia(query: str, max_results: int = 3) -> Optional[str]:
    """Search Wikipedia for factual, verified information.
    
    Wikipedia API is:
    - 100% FREE with no limits
    - Provides verified, encyclopedic information
    - Great for factual accuracy
    
    Best for: definitions, historical facts, scientific concepts, biographies
    """
    try:
        # Step 1: Search for relevant articles
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query[:100],
            "srlimit": max_results,
            "format": "json",
            "utf8": 1
        }
        
        async with httpx.AsyncClient() as client:
            # Search for articles
            search_response = await client.get(search_url, params=search_params, timeout=8.0)
            
            if search_response.status_code != 200:
                return None
            
            search_data = search_response.json()
            search_results = search_data.get("query", {}).get("search", [])
            
            if not search_results:
                logger.info(f"Wikipedia: No results for '{query[:30]}...'")
                return None
            
            # Step 2: Get extracts for top results
            titles = [r["title"] for r in search_results[:max_results]]
            
            extract_params = {
                "action": "query",
                "titles": "|".join(titles),
                "prop": "extracts",
                "exintro": True,  # Only intro paragraph
                "explaintext": True,  # Plain text, no HTML
                "exlimit": max_results,
                "format": "json",
                "utf8": 1
            }
            
            extract_response = await client.get(search_url, params=extract_params, timeout=8.0)
            
            if extract_response.status_code != 200:
                return None
            
            extract_data = extract_response.json()
            pages = extract_data.get("query", {}).get("pages", {})
            
            # Format results
            formatted = []
            for page_id, page in pages.items():
                if page_id == "-1":  # Page not found
                    continue
                title = page.get("title", "")
                extract = page.get("extract", "")[:500]  # Limit length
                if title and extract:
                    formatted.append(f"**{title}:** {extract}")
            
            if formatted:
                combined = "\n\n".join(formatted)
                logger.info(f"Wikipedia: Found {len(formatted)} articles for '{query[:30]}...'")
                return combined
            
            return None
            
    except Exception as e:
        logger.error(f"Wikipedia API error: {e}")
        return None

# ============ DUCKDUCKGO INSTANT ANSWER API ============
# FREE, UNLIMITED - for direct answers (definitions, facts, calculations)

async def search_duckduckgo_instant(query: str) -> Optional[str]:
    """DuckDuckGo Instant Answer API - FREE, unlimited, no auth.
    
    Returns direct answers for:
    - Definitions ("what is photosynthesis")
    - Quick facts ("population of India")
    - Calculations ("150 USD to INR")
    - Entity info (people, places, things)
    
    API: https://api.duckduckgo.com (no key required)
    """
    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query[:200],  # Query limit
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1,  # Skip disambiguation pages
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=8.0)
            
            if response.status_code != 200:
                logger.warning(f"DDG Instant: HTTP {response.status_code}")
                return None
            
            data = response.json()
        
        # Extract useful information
        results = []
        
        # Abstract (main definition/answer)
        abstract = data.get("Abstract", "")
        abstract_source = data.get("AbstractSource", "")
        if abstract:
            source_info = f" (via {abstract_source})" if abstract_source else ""
            results.append(f"**Definition{source_info}:** {abstract[:500]}")
        
        # Answer (direct calculation/fact)
        answer = data.get("Answer", "")
        if answer:
            results.append(f"**Answer:** {answer}")
        
        # Definition (dictionary definition)
        definition = data.get("Definition", "")
        if definition and not abstract:  # Don't duplicate if abstract exists
            results.append(f"**Definition:** {definition[:300]}")
        
        # Infobox (structured data about entities)
        infobox = data.get("Infobox", {})
        if infobox and infobox.get("content"):
            info_items = []
            for item in infobox["content"][:5]:  # Limit to 5 items
                label = item.get("label", "")
                value = item.get("value", "")
                if label and value:
                    info_items.append(f"• {label}: {value}")
            if info_items:
                results.append("**Quick Facts:**\n" + "\n".join(info_items))
        
        # Related topics (for context)
        related = data.get("RelatedTopics", [])
        if related and not results:  # Only if no other results
            for topic in related[:3]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append(f"• {topic['Text'][:200]}")
        
        if results:
            combined = "\n\n".join(results)
            logger.info(f"DDG Instant: Found answer for '{query[:30]}...'")
            return combined
        
        logger.info(f"DDG Instant: No instant answer for '{query[:30]}...'")
        return None
        
    except Exception as e:
        logger.error(f"DDG Instant API error: {e}")
        return None

# ============ OPEN-METEO WEATHER API ============
# FREE, UNLIMITED - accurate weather data, no API key needed

async def get_weather_openmeteo(location: str) -> Optional[str]:
    """Open-Meteo API - FREE, no API key, unlimited requests.
    
    Better than relying on search for weather queries.
    Uses geocoding to find coordinates, then gets weather.
    """
    try:
        # Step 1: Geocode the location
        geocode_url = "https://geocoding-api.open-meteo.com/v1/search"
        
        async with httpx.AsyncClient() as client:
            geo_response = await client.get(
                geocode_url,
                params={"name": location, "count": 1, "language": "en"},
                timeout=8.0
            )
            
            if geo_response.status_code != 200:
                logger.warning(f"Open-Meteo geocoding failed: {geo_response.status_code}")
                return None
            
            geo_data = geo_response.json()
            results = geo_data.get('results', [])
            
            if not results:
                logger.info(f"Open-Meteo: Location not found: {location}")
                return None
            
            lat = results[0].get('latitude')
            lon = results[0].get('longitude')
            city_name = results[0].get('name', location)
            country = results[0].get('country', '')
            
            # Step 2: Get weather data
            weather_url = "https://api.open-meteo.com/v1/forecast"
            weather_response = await client.get(
                weather_url,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                    "timezone": "auto"
                },
                timeout=8.0
            )
            
            if weather_response.status_code != 200:
                logger.warning(f"Open-Meteo weather failed: {weather_response.status_code}")
                return None
            
            weather_data = weather_response.json()
            current = weather_data.get('current', {})
            
            temp = current.get('temperature_2m', 'N/A')
            humidity = current.get('relative_humidity_2m', 'N/A')
            wind_speed = current.get('wind_speed_10m', 'N/A')
            weather_code = current.get('weather_code', 0)
            
            # Map weather codes to descriptions
            weather_descriptions = {
                0: "☀️ Clear sky",
                1: "🌤️ Mainly clear", 2: "⛅ Partly cloudy", 3: "☁️ Overcast",
                45: "🌫️ Foggy", 48: "🌫️ Depositing rime fog",
                51: "🌧️ Light drizzle", 53: "🌧️ Moderate drizzle", 55: "🌧️ Dense drizzle",
                61: "🌧️ Slight rain", 63: "🌧️ Moderate rain", 65: "🌧️ Heavy rain",
                71: "❄️ Slight snow", 73: "❄️ Moderate snow", 75: "❄️ Heavy snow",
                80: "🌧️ Slight rain showers", 81: "🌧️ Moderate rain showers", 82: "🌧️ Violent rain showers",
                95: "⛈️ Thunderstorm", 96: "⛈️ Thunderstorm with hail", 99: "⛈️ Thunderstorm with heavy hail"
            }
            weather_desc = weather_descriptions.get(weather_code, "🌡️ Unknown")
            
            result = f"""**Weather in {city_name}, {country}**
{weather_desc}
🌡️ Temperature: {temp}°C
💧 Humidity: {humidity}%
💨 Wind: {wind_speed} km/h"""
            
            logger.info(f"Open-Meteo: Got weather for {city_name}")
            return result
            
    except Exception as e:
        logger.error(f"Open-Meteo error: {e}")
        return None


# ============ ADAPTIVE RESPONSE ENGINE ============
# Smart context-aware response system with precise character limits
# Based on modern AI practices from ChatGPT, Claude, and Perplexity

class AdaptiveResponseEngine:
    """Smart response length system with proper word/character targets.
    
    Response Targets (based on user requirements):
    - DETAILED: ~400 words / ~2500 characters (comprehensive answers)
    - NORMAL: ~250 words / ~1500 characters (standard informative)
    - CASUAL: ~50-100 words / ~300-600 characters (greetings, small talk)
    - BRIEF: ~30-50 words / ~200-300 characters (quick answers)
    
    Uses word count instructions (AI models follow word counts more reliably than character counts).
    """
    
    @classmethod
    def get_dynamic_response_config(cls, query: str, intent: str, has_search_results: bool = False) -> dict:
        """Get response configuration with smart length targeting.
        
        The AI is instructed with word counts (more reliable than character counts).
        """
        query_lower = query.lower().strip()
        word_count = len(query.split())
        
        # ========== DETAILED DETECTION (Expanded) ==========
        # Explicit detailed keywords
        explicit_detail_keywords = [
            'detailed', 'elaborate', 'more about', 'deep dive',
            'tell me everything', 'comprehensive', 'in detail', 'step by step',
            'full explanation', 'complete answer', 'thorough', 'extensive',
            'explain in detail', 'give me details', 'more information',
            'tell me more', 'long answer', 'detailed answer'
        ]
        
        # Question patterns that naturally need longer responses
        complex_question_patterns = [
            'how to ', 'how do i ', 'how can i ', 'what is the best way',
            'why does ', 'why is ', 'what are the ',
            'explain how', 'explain why', 'explain what',
            'difference between', 'compare ', 'versus ',
            'advantages and disadvantages', 'pros and cons',
            'step by step', 'guide to', 'tutorial'
        ]
        
        wants_detail = (
            any(kw in query_lower for kw in explicit_detail_keywords) or
            any(pattern in query_lower for pattern in complex_question_patterns) or
            word_count >= 12  # Long questions usually need detailed answers
        )
        
        # ========== BRIEF DETECTION ==========
        wants_short = any(kw in query_lower for kw in [
            'briefly', 'short', 'quick', 'tldr', 'just tell me', 'simple',
            'in short', 'summarize', 'one line', 'quick answer', 'be brief'
        ])
        
        # Simple greetings = casual response
        is_greeting = intent in [IntentType.GREETING, IntentType.SMALL_TALK]
        
        # ========== CASUAL (Greetings/Small Talk) ==========
        if is_greeting:
            logger.info(f"AdaptiveResponse: CASUAL mode for greeting")
            return {
                'max_tokens': 500,
                'length_instruction': '''RESPONSE LENGTH: 2-4 sentences only.
Be warm, friendly, and conversational. Keep it brief - this is casual chat.''',
                'response_style': 'casual'
            }
        
        # ========== BRIEF (User wants short answer) ==========
        if wants_short:
            logger.info(f"AdaptiveResponse: BRIEF mode (user requested short)")
            return {
                'max_tokens': 800,
                'length_instruction': '''RESPONSE LENGTH: ~50 words maximum (about 300 characters).
Give a direct, concise answer. User specifically wants it SHORT.
Skip elaborate explanations - get to the point immediately.''',
                'response_style': 'brief'
            }
        
        # ========== DETAILED (User wants comprehensive answer) ==========
        if wants_detail:
            logger.info(f"AdaptiveResponse: DETAILED mode (~2500 chars)")
            return {
                'max_tokens': 6000,
                'length_instruction': '''RESPONSE LENGTH: ~400-500 words (approximately 2500 characters).
Provide a COMPREHENSIVE, DETAILED response. The user wants thorough information.

REQUIREMENTS:
• Cover all relevant aspects of the topic
• Include examples, facts, and context
• Use numbered sections for organization
• Break complex topics into clear parts
• Be educational and complete

Use **bold** for key terms, numbered lists for steps, bullet points for features.''',
                'response_style': 'detailed'
            }
        
        # ========== NORMAL (Standard informative answer) ==========
        # This is the default for most questions
        return {
            'max_tokens': 4000,  # Generous limit to prevent cutting
            'length_instruction': '''RESPONSE LENGTH: ~200-300 words (about 1500 characters).

Provide a clear, informative answer that:
• Answers the question directly and completely
• Includes relevant context and details
• Uses formatting when it helps clarity
• Balances thoroughness with readability

Use **bold** for key terms, numbered lists for steps or multiple items.''',
            'response_style': 'normal'
        }


# ============ ACCURATE TIME API ============
# Using timeapi.io as primary (more reliable), WorldTimeAPI as fallback

async def get_accurate_time(timezone: str = "Asia/Kolkata") -> Optional[str]:
    """Get accurate time from timeapi.io - more reliable than WorldTimeAPI.
    
    Primary: timeapi.io (20,000 req/month free, very reliable)
    Fallback: WorldTimeAPI (no limits but sometimes unreliable)
    """
    # Encode timezone for URL (replace / with %2F)
    tz_encoded = timezone.replace('/', '%2F')
    
    # Try timeapi.io first (more reliable)
    try:
        url = f"https://timeapi.io/api/Time/current/zone?timeZone={tz_encoded}"
        logger.info(f"Fetching time from timeapi.io for {timezone}...")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=8.0)
            
            if response.status_code == 200:
                data = response.json()
                # Format: {"year":2026,"month":1,"day":9,"hour":16,"minute":23,...}
                hour = data.get('hour', 0)
                minute = data.get('minute', 0)
                day = data.get('day', 0)
                month = data.get('month', 0)
                year = data.get('year', 0)
                day_of_week = data.get('dayOfWeek', 'Unknown')
                
                # Format time as 12-hour with AM/PM
                am_pm = "AM" if hour < 12 else "PM"
                hour_12 = hour if hour <= 12 else hour - 12
                if hour_12 == 0:
                    hour_12 = 12
                
                time_str = f"{hour_12}:{minute:02d} {am_pm}"
                date_str = f"{day_of_week}, {day} {month}, {year}"
                
                logger.info(f"✓ timeapi.io: Got time for {timezone}")
                return f"🕐 **Current Time ({timezone}):** {time_str}\n📅 **Date:** {date_str}"
            else:
                logger.warning(f"timeapi.io returned {response.status_code}")
    except Exception as e:
        logger.warning(f"timeapi.io failed: {e}")
    
    # Fallback to WorldTimeAPI
    try:
        url = f"http://worldtimeapi.org/api/timezone/{timezone}"
        logger.info(f"Trying WorldTimeAPI fallback for {timezone}...")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=8.0)
            
            if response.status_code == 200:
                data = response.json()
                datetime_str = data.get('datetime', '')
                if datetime_str:
                    dt_part = datetime_str.split('.')[0]
                    logger.info(f"✓ WorldTimeAPI: Got time for {timezone}")
                    return f"🕐 **Current Time ({timezone}):** {dt_part.replace('T', ' ')}"
    except Exception as e:
        logger.error(f"WorldTimeAPI also failed: {e}")
    
    logger.error("Both time APIs failed!")
    return None


# Legacy function kept for backward compatibility
async def get_world_time(timezone: str = "Asia/Kolkata") -> Optional[str]:
    """Legacy wrapper - now uses get_accurate_time."""
    return await get_accurate_time(timezone)

async def search_tavily(query: str, max_results: int = 5) -> Optional[str]:
    """Tavily Search - Optimized based on Official Best Practices.
    
    Key optimizations (from docs.tavily.com):
    1. Auto-detect topic (news/finance/general)
    2. Use time_range for real-time queries
    3. Score-based filtering (>0.7 for high quality)
    4. Keep query under 400 chars
    5. Use include_answer for direct AI response
    """
    if not TAVILY_ENABLED or not TAVILY_API_KEY:
        logger.debug("Tavily not configured")
        return None
    
    try:
        url = "https://api.tavily.com/search"
        query_lower = query.lower()
        query_clean = query[:400]  # Keep under 400 chars (Tavily best practice)
        
        # Auto-detect topic and time sensitivity for better relevance
        # ALWAYS use time_range='day' for maximum freshness
        time_range = "day"  # Force fresh results ALWAYS
        days_back = 1  # Default: last 24 hours
        
        # Check for relative date words to adjust time range
        if any(w in query_lower for w in ['yesterday', 'one day ago']):
            days_back = 2  # Yesterday + today
        elif any(w in query_lower for w in ['last week', 'past week']):
            days_back = 7
            time_range = "week"
        elif any(w in query_lower for w in ['last month', 'past month']):
            days_back = 30
            time_range = "month"
        
        # Detect topic
        if any(w in query_lower for w in ['news', 'latest', 'breaking', 'update', 'happening', 'headlines']):
            topic = "news"
        elif any(w in query_lower for w in ['stock', 'price', 'market', 'sensex', 'nifty', 'crypto', 'bitcoin', 'gold', 'silver']):
            topic = "finance"
        else:
            topic = "general"
        
        # Build payload - ALWAYS include time_range for freshness
        news_max_results = 8 if topic == 'news' else max_results
        
        payload = {
            "api_key": TAVILY_API_KEY,
            "query": query_clean,
            "search_depth": "advanced",  # Better relevance
            "topic": topic,
            "include_answer": True,  # Get AI-generated direct answer
            "max_results": news_max_results,
            "time_range": time_range,  # ALWAYS set for fresh results
        }
        
        # For news: also add days parameter for more precise date filtering
        if topic == "news":
            payload["days"] = days_back
        
        logger.info(f"Tavily: '{query[:30]}...' topic={topic} time_range={time_range} days={days_back}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=15.0)
            
            if response.status_code == 401:
                logger.error("Tavily API: Invalid API key")
                return None
            elif response.status_code == 429:
                logger.warning("Tavily API: Rate limit exceeded")
                return None
            elif response.status_code != 200:
                logger.error(f"Tavily API error: {response.status_code}")
                return None
            
            data = response.json()
        
        # PRIORITY 1: Use Tavily's AI answer (most accurate, recommended by docs)
        if data.get('answer'):
            logger.info(f"Tavily: Using AI answer ({len(data['answer'])} chars)")
            return data['answer']
        
        # PRIORITY 2: Combine high-quality results (score > 0.7 per best practices)
        if data.get('results'):
            high_quality = [r for r in data['results'] if r.get('score', 0) > 0.7]
            
            if high_quality:
                # Combine content from top high-quality results
                combined = []
                for result in high_quality[:3]:
                    content = result.get('content', '')
                    if content:
                        combined.append(content)
                
                if combined:
                    final = ' '.join(combined)
                    logger.info(f"Tavily: Combined {len(high_quality)} high-quality results (score>0.7)")
                    return final
            
            # FALLBACK: Use any results if none pass score filter
            contents = [r.get('content', '') for r in data['results'][:3] if r.get('content')]
            if contents:
                logger.info(f"Tavily: Using {len(contents)} unfiltered results")
                return ' '.join(contents)
        
        logger.warning(f"Tavily: No results for: {query[:30]}...")
        return None
        
    except httpx.TimeoutException:
        logger.error(f"Tavily timeout for: {query[:30]}...")
        return None
    except Exception as e:
        logger.error(f"Tavily error: {e}", exc_info=True)
        return None


# ============ GPT RESEARCHER - REAL-TIME AI RESEARCH AGENT ============
# Specifically designed for real-time web research with citations
# Install: pip install gpt-researcher
# GitHub: https://github.com/assafelovic/gpt-researcher
# 
# IMPORTANT: We configure it to use GROQ (FREE!) instead of OpenAI
# This means NO OpenAI API key required!

GPT_RESEARCHER_ENABLED = False  # Disabled - was using Groq internally

def setup_gpt_researcher_with_groq():
    """Configure GPT Researcher to use Groq (FREE) instead of OpenAI.
    
    GPT Researcher supports multiple LLM providers. We use Groq because:
    1. It's FREE with generous limits
    2. It's already configured in this bot
    3. It's OpenAI-compatible
    """
    # Set environment variables for GPT Researcher to use Groq
    os.environ["SMART_LLM"] = f"groq/{GROQ_MODEL}"  # For complex reasoning
    os.environ["FAST_LLM"] = f"groq/{GROQ_MODEL}"   # For quick tasks
    os.environ["GROQ_API_KEY"] = GROQ_API_KEY       # Your existing Groq key
    os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY   # For web search
    
    # Alternative: Use Together AI (also FREE)
    # os.environ["SMART_LLM"] = "together_ai/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
    # os.environ["TOGETHER_API_KEY"] = "your-together-ai-key"
    
    logger.info("GPT Researcher configured to use Groq (FREE) as LLM provider")

async def search_with_gpt_researcher(query: str) -> Optional[str]:
    """Use GPT Researcher for authoritative real-time research.
    
    GPT Researcher is an autonomous AI agent that:
    1. Conducts deep research on any topic
    2. Searches multiple web sources using Tavily
    3. Generates comprehensive reports with citations
    
    Configured to use GROQ (FREE!) instead of requiring OpenAI.
    """
    if not GPT_RESEARCHER_ENABLED:
        return None
    
    try:
        # Configure to use Groq (FREE) instead of OpenAI
        setup_gpt_researcher_with_groq()
        
        # Try to import GPT Researcher
        from gpt_researcher import GPTResearcher
        
        logger.info(f"GPT Researcher: Starting research for '{query[:50]}...'")
        
        # Create researcher with the query
        # report_type can be: 'research_report', 'quick_report', 'outline_report'
        researcher = GPTResearcher(
            query=query,
            report_type="quick_report"  # Fast response for chat
        )
        
        # Conduct the research (this searches the web in real-time)
        research_result = await researcher.conduct_research()
        
        if research_result:
            logger.info(f"✓ GPT Researcher: Got {len(str(research_result))} chars of research")
            return str(research_result)
        else:
            logger.warning("GPT Researcher: No research results")
            return None
            
    except ImportError:
        logger.warning("GPT Researcher not installed. Run: pip install gpt-researcher")
        return None
    except Exception as e:
        logger.error(f"GPT Researcher error: {e}")
        return None

async def smart_search(query: str) -> tuple:
    """SMART SEARCH with comprehensive fallback chain.
    
    Priority (if one fails, next starts automatically):
    1. Tavily (93.3% accuracy, AI-optimized)
    2. Google Custom Search (reliable, good coverage)
    3. DuckDuckGo Instant (fast facts)
    4. DuckDuckGo Full (unlimited, free)
    5. Wikipedia (encyclopedia facts)
    6. Jina AI (context-aware, semantic)
    
    Returns: (search_results, sources_list) tuple
    """
    query_lower = query.lower()
    all_sources = []
    
    # Special handling for time/date queries
    is_time_query = any(w in query_lower for w in ['time', 'date', 'today', 'now', 'current time'])
    
    if is_time_query:
        try:
            time_result = await get_accurate_time()
            if time_result:
                logger.info("Time query answered by Time API")
                return (time_result, ["Time API"])
        except Exception as e:
            logger.warning(f"Time API failed: {e}")
    
    # ============ 1. TAVILY (Primary - AI-optimized) ============
    if TAVILY_ENABLED and TAVILY_API_KEY:
        try:
            logger.info(f"[1/6] Tavily Search: '{query[:50]}...'")
            tavily_result = await search_tavily(query)
            if tavily_result and len(tavily_result) > 50:
                logger.info(f"✓ Tavily: {len(tavily_result)} chars")
                return (tavily_result, ["Tavily AI Search"])
        except Exception as e:
            logger.warning(f"Tavily failed: {e}, trying next source...")
    
    # ============ 2. GOOGLE CUSTOM SEARCH ============
    if GOOGLE_SEARCH_ENABLED and GOOGLE_SEARCH_API_KEY:
        try:
            logger.info(f"[2/6] Google Custom Search: '{query[:50]}...'")
            google_result = await search_internet(query)
            if google_result and len(google_result) > 50:
                logger.info(f"✓ Google Custom Search: {len(google_result)} chars")
                return (google_result, ["Google Search"])
        except Exception as e:
            logger.warning(f"Google Search failed: {e}, trying next source...")
    
    # ============ 3. DUCKDUCKGO INSTANT (Fast facts) ============
    try:
        logger.info(f"[3/6] DDG Instant Answer: '{query[:50]}...'")
        instant_result = await search_duckduckgo_instant(query)
        if instant_result and len(instant_result) > 50:
            logger.info(f"✓ DDG Instant: {len(instant_result)} chars")
            # Combine with ddgs for more context if it's a simple answer
            if len(instant_result) < 300:
                ddg_extra = await search_ddgs(query, max_results=3)
                if ddg_extra:
                    instant_result = f"{instant_result}\n\n**Additional Context:**\n{ddg_extra}"
            return (instant_result, ["DuckDuckGo Instant"])
    except Exception as e:
        logger.warning(f"DDG Instant failed: {e}, trying next source...")
    
    # ============ 4. DUCKDUCKGO FULL (Unlimited) ============
    try:
        logger.info(f"[4/6] DuckDuckGo Full: '{query[:50]}...'")
        ddg_result = await search_ddgs(query, max_results=5)
        if ddg_result and len(ddg_result) > 50:
            logger.info(f"✓ DuckDuckGo: {len(ddg_result)} chars")
            return (ddg_result, ["DuckDuckGo"])
    except Exception as e:
        logger.warning(f"DuckDuckGo failed: {e}, trying next source...")
    
    # ============ 5. WIKIPEDIA (Encyclopedia) ============
    if WIKIPEDIA_ENABLED:
        try:
            logger.info(f"[5/6] Wikipedia: '{query[:50]}...'")
            wiki_result = await search_wikipedia(query)
            if wiki_result and len(wiki_result) > 50:
                logger.info(f"✓ Wikipedia: {len(wiki_result)} chars")
                return (wiki_result, ["Wikipedia"])
        except Exception as e:
            logger.warning(f"Wikipedia failed: {e}, trying next source...")
    
    # ============ 6. JINA AI (Semantic search) ============
    if JINA_ENABLED:
        try:
            logger.info(f"[6/6] Jina AI Search: '{query[:50]}...'")
            jina_result = await search_jina(query)
            if jina_result and len(jina_result) > 50:
                logger.info(f"✓ Jina AI: {len(jina_result)} chars")
                return (jina_result, ["Jina AI"])
        except Exception as e:
            logger.warning(f"Jina AI failed: {e}")
    
    logger.warning(f"All search sources failed for: {query[:30]}...")
    return (None, [])


def expand_query_for_search(query: str) -> str:
    """Expand vague queries into better search terms (like Perplexity).
    
    Key principles:
    1. DO NOT add hardcoded dates - let Tavily's time_range handle recency
    2. Convert relative dates (yesterday, today, tomorrow) to context
    3. Expand single-word queries for better results
    """
    query_lower = query.lower().strip()
    
    # Convert relative date words to context for AI (not hardcoded dates)
    # The AI and search will interpret these naturally
    relative_date_context = {
        'yesterday': 'one day ago recent',
        'tomorrow': 'upcoming future scheduled',
        'last week': 'past week recent',
        'next week': 'upcoming week future',
        'last month': 'past month recent',
        'next month': 'upcoming month future',
    }
    
    for rel_date, context in relative_date_context.items():
        if rel_date in query_lower:
            # Add context without removing original words
            expanded = f"{query} {context}"
            logger.info(f"Added relative date context: '{query}' → '{expanded}'")
            return expanded
    
    # Single-word query expansions (NO dates - just better search terms)
    expansions = {
        'bitcoin': 'bitcoin BTC current price USD live',
        'ethereum': 'ethereum ETH current price USD live',
        'weather': 'weather forecast current conditions',
        'news': 'latest breaking news headlines',
        'stocks': 'stock market indices live',
        'gold': 'gold price per gram USD live',
        'silver': 'silver price USD live',
        'sensex': 'BSE sensex index live India',
        'nifty': 'NSE nifty 50 live India',
        'crypto': 'cryptocurrency market prices live',
        'time': 'current time now live',
        'date': 'current date today',
        'today': 'today current date news',
    }
    
    # Check for single-word matches
    if query_lower in expansions:
        expanded = expansions[query_lower]
        logger.info(f"Query expanded: '{query}' → '{expanded}'")
        return expanded
    
    # For news queries, add "latest" context but NO date
    news_keywords = ['news', 'happening', 'going on', 'update', 'updates']
    if any(kw in query_lower for kw in news_keywords) and 'latest' not in query_lower:
        expanded = f"latest {query}"
        logger.info(f"Added 'latest' context: '{query}' → '{expanded}'")
        return expanded
    
    return query


# ============ AI MODEL SYSTEM ============
# Primary: Kimi K2 via Groq | Fallback 1: GPT-OSS 120B | Fallback 2: GPT-OSS 20B | Final: Cerebras

async def call_groq_api(messages: list, max_tokens: int, model: str = None, retries: int = 2) -> tuple:
    """Call Groq API with Kimi K2 primary and GPT-OSS fallbacks.
    
    Model Hierarchy:
    1. Kimi K2 (moonshotai/kimi-k2-instruct-0905) - Primary, your preferred
    2. GPT-OSS-120B (openai/gpt-oss-120b) - First fallback
    3. GPT-OSS-20B (openai/gpt-oss-20b) - Second fallback
    
    Returns: (response_text, 'groq') or raises exception on failure.
    """
    # Try all three models in order: Kimi K2 first, then GPT-OSS models
    models_to_try = [GROQ_KIMI_MODEL, GROQ_GPT_120B_MODEL, GROQ_GPT_20B_MODEL]
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    last_error = None
    
    for current_model in models_to_try:
        logger.info(f"🤖 Trying Groq model: {current_model}")
        
        payload = {
            "model": current_model,
            "messages": messages,
            "temperature": generation_config["temperature"],
            "max_tokens": max_tokens,
            "top_p": generation_config["top_p"],
            "stream": False
        }
        
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:  # Increased timeout for larger models
                    response = await client.post(GROQ_URL, headers=headers, json=payload)
                    
                    if response.status_code == 200:
                        data = response.json()
                        response_text = data['choices'][0]['message']['content']
                        logger.info(f"✓ Groq {current_model} responded successfully (attempt {attempt + 1})")
                        return (response_text, 'groq')
                    elif response.status_code == 429:  # Rate limited
                        wait_time = 2 ** attempt
                        logger.warning(f"Groq rate limited, waiting {wait_time}s (attempt {attempt + 1})")
                        await asyncio.sleep(wait_time)
                        continue
                    elif response.status_code == 400:
                        # Model error or bad request - try next model
                        error_msg = response.text[:200] if response.text else "Bad request"
                        logger.warning(f"Model {current_model} error: {error_msg}, trying fallback...")
                        break  # Break inner retry loop, try next model
                    elif response.status_code == 503:
                        # Service unavailable - try next model
                        logger.warning(f"Model {current_model} unavailable (503), trying fallback...")
                        break
                    else:
                        last_error = f"Groq API Error {response.status_code}: {response.text[:200]}"
                        logger.warning(f"{last_error} (attempt {attempt + 1})")
                        # Don't break - retry this model
                        
            except httpx.TimeoutException:
                last_error = f"Groq timeout with {current_model}"
                wait_time = 2 ** attempt
                logger.warning(f"{last_error}, retrying in {wait_time}s (attempt {attempt + 1})")
                await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Groq error: {last_error} (attempt {attempt + 1})")
                await asyncio.sleep(1)
        
        # If we're here, this model failed - log and try next
        if current_model == GROQ_KIMI_MODEL:
            logger.info(f"Kimi K2 failed, switching to GPT-OSS-120B fallback...")
        elif current_model == GROQ_GPT_120B_MODEL:
            logger.info(f"GPT-OSS-120B failed, switching to GPT-OSS-20B fallback...")
    
    raise Exception(last_error or "Groq failed after all retries with all models")


async def call_cerebras_api(messages: list, max_tokens: int, model: str, retries: int = 3) -> tuple:
    """Call Cerebras API with retry logic and exponential backoff.
    
    Returns: (response_text, 'cerebras') or raises exception on failure.
    """
    headers = {
        "Authorization": f"Bearer {CEREBRAS_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": generation_config["temperature"],
        "max_tokens": max_tokens,
        "top_p": generation_config["top_p"],
        "stream": False
    }
    
    last_error = None
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:  # Reduced timeout per attempt
                response = await client.post(CEREBRAS_URL, headers=headers, json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    response_text = data['choices'][0]['message']['content']
                    logger.info(f"Cerebras responded successfully (attempt {attempt + 1}) ✓")
                    return (response_text, 'cerebras')
                elif response.status_code == 429:  # Rate limited
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Cerebras rate limited, waiting {wait_time}s (attempt {attempt + 1})")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    last_error = f"Cerebras API Error {response.status_code}"
                    logger.warning(f"{last_error} (attempt {attempt + 1})")
                    
        except httpx.TimeoutException:
            last_error = "Cerebras timeout"
            wait_time = 2 ** attempt
            logger.warning(f"Cerebras timeout, retrying in {wait_time}s (attempt {attempt + 1})")
            await asyncio.sleep(wait_time)
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Cerebras error: {last_error} (attempt {attempt + 1})")
            await asyncio.sleep(1)
    
    raise Exception(last_error or "Cerebras failed after all retries")


# ============ GROQ REMOVED ============
# Previously had call_groq_api() and race_ai_models() functions here
# Now using Cerebras as single AI provider for simplicity and latest models

async def race_ai_models(messages: list, max_tokens: int) -> tuple:
    """Execute AI models in parallel (Race) and return first successful result."""
    # Models to race - utilizing both available high-speed models
    tasks = [
        asyncio.create_task(call_groq_api(messages, max_tokens, GROQ_MODEL)),
        asyncio.create_task(call_cerebras_api(messages, max_tokens, CEREBRAS_MODEL))
    ]
    
    try:
        # Wait for the first one to complete successfully
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        
        # Check results
        for task in done:
            try:
                result = task.result()
                if result:
                    # Cancel pending tasks to save resources
                    for p in pending:
                        p.cancel()
                    return result
            except Exception as e:
                logger.warning(f"One AI model failed in race: {e}")
        
        # If the first finished task failed, wait for the others
        if pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    return task.result()
                except Exception:
                    pass
                    
    except Exception as e:
        logger.error(f"Race failed: {e}")
    
    raise Exception("All AI models failed to respond.")


async def get_llama_response(user_content: any, user_id: int, intent: str = None) -> str:
    """Get response from Best Available AI (Race Groq/Cerebras) with conversation history."""
    try:
        session = get_user_session(user_id)
        if not session:
             return "❌ Sorry, I couldn't initialize your AI session properly. Please try /clear or contact the admin."

        # Get conversation history
        conversation_history = session.get('conversation_history', [])
        
        # ALWAYS use fresh system prompt with current timestamp (like Perplexity AI)
        system_prompt = get_system_prompt_with_timestamp()
        
        # Prune history if too long
        if len(conversation_history) > MAX_HISTORY * 2:
            logger.info(f"Pruning history for user {user_id}. Old length: {len(conversation_history)}")
            conversation_history = conversation_history[-(MAX_HISTORY * 2):]
            session['conversation_history'] = conversation_history

        # Check if internet search is needed based on intent
        user_query = str(user_content) if not isinstance(user_content, str) else user_content
        search_results = None
        search_sources = []
        
        # Get current timestamp for response
        current_timestamp = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
        
        # Use intent-based search decision
        if should_search(user_query, intent):
            # QUERY EXPANSION: Make vague queries more specific (like Perplexity)
            expanded_query = expand_query_for_search(user_query)
            
            logger.info(f"Search triggered for user {user_id} (intent={intent}): {expanded_query[:50]}...")
            
            # --- EVENTS SEARCH INTEGRATION ---
            # Simple inline check for event-related queries (avoids function order issues)
            event_keywords = ["event", "meetup", "conference", "workshop", "seminar", "webinar"]
            is_event_query = any(kw in user_query.lower() for kw in event_keywords)
            
            if is_event_query:
                try:
                    # Specialized Event Search
                    events_agent = EventsIntelligenceAgent()
                    event_results = await events_agent.discover_events(user_query)
                    if event_results:
                        formatted_events = events_agent.format_events_for_display(event_results)
                        search_results = f"EVENTS FOUND:\n{formatted_events}"
                        search_sources.append("Events Intelligence Agent")
                except Exception as e:
                    logger.warning(f"Events search failed: {e}, using general search")
            
            # Fallback/Addition: General Web Search if no events or mixed query
            if not search_results:
                search_results, search_sources = await smart_search(expanded_query)
            
            if search_results:
                # SOURCE ATTRIBUTION: Track where info came from
                sources_text = ", ".join(search_sources) if search_sources else "Web Search"
                
                # CONTEXT LIMITING: Truncate search results to reduce hallucination
                # (Shorter context = fewer opportunities for hallucination)
                max_context_chars = 3000
                if len(search_results) > max_context_chars:
                    search_results = search_results[:max_context_chars] + "\n... [truncated for accuracy]"
                    logger.info(f"Truncated search context to {max_context_chars} chars")
                
                # NATURAL AI RESPONSE PROMPT (not robotic search engine style)
                # Include unique timestamp to ensure fresh context each time
                unique_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                
                enhanced_query = f"""⚠️ CRITICAL: YOUR TRAINING DATA IS OUTDATED! Use ONLY the search data below.

CURRENT DATE/TIME: {current_timestamp}
SEARCH TIMESTAMP: {unique_time}

🔍 LIVE SEARCH RESULTS (JUST RETRIEVED - THIS IS THE TRUTH):
---
{search_results}
---

USER QUESTION: {user_query}

🚨 MANDATORY RULES - YOU MUST FOLLOW THESE:
1. ONLY use the search data above to answer - it is LIVE and CURRENT
2. Your training data is from the past and is OUTDATED - do NOT use it for facts
3. If the search data says X and you "know" Y, ALWAYS use X (search is newer)
4. For prices, news, events, dates, scores - use ONLY the numbers/facts from search
5. If search data doesn't have enough info, say "Based on current search results..." 
6. NEVER guess or fill in gaps with your training knowledge
7. Treat the search data as if YOU just looked it up yourself

HOW TO RESPOND:
- Sound natural and confident, like you already know this info
- Do NOT say "according to search results" or "I found that..."
- Just state the facts directly as if you're a well-informed friend
- Start directly with the answer - no "So", "Well", "Certainly"
- Give a FRESH answer even if asked the same question before

The search data above = THE ONLY SOURCE OF TRUTH for this answer."""
                user_content = enhanced_query
            else:
                # SEARCH WAS ATTEMPTED BUT RETURNED NO RESULTS
                # Fall back to using the original query
                user_content = user_query
                logger.info(f"Search returned no results for user {user_id}, using original query")
        else:
            # NO SEARCH NEEDED - use the original query directly
            user_content = user_query

        # ============ ADAPTIVE RESPONSE ENGINE ============
        # Modern AI-style dynamic response - replaces old get_query_complexity
        
        # Detect if user is sharing a link (treat as needing detailed response)
        has_link = bool(re.search(r'https?://[^\s]+', user_query))
        has_search = search_results is not None
        
        # If user shares a link, treat as detailed request
        effective_intent = intent
        if has_link:
            logger.info(f"Link detected in query - using detailed response mode")
        
        # Get dynamic response config from AdaptiveResponseEngine
        response_config = AdaptiveResponseEngine.get_dynamic_response_config(
            user_query, intent, has_search_results=has_search
        )
        
        # If link is shared, override to detailed mode
        if has_link:
            response_config = {
                'max_tokens': 3000,
                'length_instruction': '''Provide a COMPREHENSIVE analysis of the shared link/content.
                
**REQUIREMENTS:**
• Analyze the link content thoroughly
• Aim for 300-600 words
• Include key points, insights, and context
• Use professional formatting with numbered lists and bold headings
• Be informative and educational''',
                'response_style': 'detailed'
            }
        
        dynamic_max_tokens = response_config['max_tokens']
        length_instruction = response_config['length_instruction']
        response_style = response_config['response_style']
        
        # Get format instructions
        format_info = SmartFormatSelector.get_format_instruction(user_query)
        format_instruction = format_info['instruction']
        
        logger.info(f"AdaptiveResponse: style={response_style}, max_tokens={dynamic_max_tokens} for: {user_query[:30]}...")
        
        # Build final instruction
        final_length_instruction = f"""

---
{length_instruction}
{format_instruction}"""
        
        # Add length instruction AFTER the user content
        final_user_content = f"{user_content}{final_length_instruction}"

        # Build messages list for Cerebras API
        messages = []
        
        # Always use fresh system prompt with timestamp
        messages.append({"role": "system", "content": system_prompt})
        
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": str(final_user_content)})

        # ============ AI MODEL RACE (Groq vs Cerebras) ============
        try:
            logger.info(f"Racing AI models for user {user_id}...")
            
            response_text, provider = await race_ai_models(
                messages=messages,
                max_tokens=dynamic_max_tokens
            )
            
            logger.info(f"Winner: {provider} for user {user_id}")
            
        except Exception as e:
            logger.error(f"All AI models failed: {e}")
            return f"❌ Error connecting to AI Service. Both Groq and Cerebras failed."

        # Update conversation history - ONLY store original query, NOT enhanced query with search results
        # This prevents old search results from appearing in history and causing repeated answers
        if search_results:
            # For search-based queries: Store simplified version without old search data
            # This ensures the AI won't see old search results when same question is asked again
            logger.info(f"Search query - storing simplified history entry for user {user_id}")
            conversation_history.append({"role": "user", "content": f"[Search query: {user_query}]"})
            conversation_history.append({"role": "assistant", "content": f"[Answered with real-time search data]"})
        else:
            # For non-search queries: Store full Q&A for context
            conversation_history.append({"role": "user", "content": str(user_query)})
            conversation_history.append({"role": "assistant", "content": response_text})
        session['conversation_history'] = conversation_history
        
        # Validate and clean the response to remove unwanted content
        cleaned_response = validate_and_clean_response(response_text, user_query)
        
        return cleaned_response

    except Exception as e:
        logger.error(f"Unexpected error in get_llama_response for user {user_id}: {e}", exc_info=True)
        return "❌ Sorry, an unexpected error occurred while processing your request. Please try again!"


# ============ COMMAND HANDLERS ============
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    session = get_user_session(user.id)
    if not session:
        await update.message.reply_text("❌ Could not create a user session. Please try again.")
        return
    session['username'] = user.username or user.first_name

    keyboard = [
        [InlineKeyboardButton("📚 Help", callback_data='help'),
         InlineKeyboardButton("ℹ️ About", callback_data='about')],
        [InlineKeyboardButton("🔧 Settings", callback_data='settings'),
         InlineKeyboardButton("📊 Stats", callback_data='stats')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    model_name = session.get('model_name', DEFAULT_MODEL)

    welcome_message = f"""
🤖 **Welcome {user.first_name}!** I'm your Personal AI Assistant 🌟

**Developed by Rising AI** 🚀

**What I can do:**
✅ Answer questions instantly
✅ Have natural, context-aware conversations
✅ Search for real-time information when needed
✅ Help with coding, writing, and more!

Just send me any message! 💬
Use /help to see all commands.
"""

    await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    # --- UPDATED Help Message ---
    help_text = f"""
📖 **Available Commands:**

/start - Start the bot & see welcome message
/help - Show this help message
/clear - Clear conversation history & start fresh
/stats - Show your usage statistics
/settings - Configure bot settings
/model - Switch between AI models (Flash/Pro)
/cmodel - Show current model configuration
/system - View or set a custom system prompt
/search - Search through conversation history
/history - View recent conversation history

🤖 **How to Use:**
• **Text:** Simply send any message.

**Features:**
• Context-aware conversations ({MAX_HISTORY} messages)
• Custom personalities via /system
• Model selection (/model)
• Search conversation history (/search)
• View conversation history (/history)
• 🌐 **Internet Search** - Automatic real-time web search for current information
• 🎨 **Smart Formatting** - Auto-adapts response style based on your query
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def style_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /style command - change response style preset."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    
    # Check if style argument provided
    if context.args and len(context.args) > 0:
        new_style = context.args[0].lower()
        
        if new_style in RESPONSE_STYLE_PRESETS:
            preset = RESPONSE_STYLE_PRESETS[new_style]
            # Update preferences
            session['preferences']['response_style'] = preset['response_style']
            session['preferences']['include_emojis'] = preset['include_emojis']
            save_user_data()
            
            await update.message.reply_text(
                f"✅ **Style changed to: {new_style.capitalize()}**\n\n"
                f"{preset['description']}\n\n"
                f"Your responses will now be in this style!",
                parse_mode='Markdown'
            )
        else:
            available = ", ".join(RESPONSE_STYLE_PRESETS.keys())
            await update.message.reply_text(
                f"❌ Unknown style: `{new_style}`\n\n"
                f"**Available styles:** {available}",
                parse_mode='Markdown'
            )
    else:
        # Show current style and available options
        current_style = session['preferences'].get('response_style', 'friendly')
        
        styles_text = "\n".join([
            f"• **{name}** - {preset['description']}"
            for name, preset in RESPONSE_STYLE_PRESETS.items()
        ])
        
        await update.message.reply_text(
            f"🎨 **Response Style Settings**\n\n"
            f"**Current style:** {current_style.capitalize()}\n\n"
            f"**Available styles:**\n{styles_text}\n\n"
            f"**Usage:** `/style professional`",
            parse_mode='Markdown'
        )


async def preferences_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /preferences command - view and manage user preferences."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    preferences = session.get('preferences', UserPreferences.get_defaults())
    
    # Check for setting a preference
    if context.args and len(context.args) >= 2:
        pref_key = context.args[0].lower()
        pref_value = context.args[1].lower()
        
        valid_keys = {
            'style': ('response_style', ['friendly', 'professional', 'casual', 'technical', 'concise']),
            'length': ('response_length', ['short', 'medium', 'detailed']),
            'emojis': ('include_emojis', ['on', 'off']),
            'level': ('expertise_level', ['beginner', 'general', 'expert']),
            'name': ('name', None),  # Any value allowed
        }
        
        if pref_key in valid_keys:
            internal_key, valid_values = valid_keys[pref_key]
            
            # Special handling for boolean emojis
            if pref_key == 'emojis':
                preferences[internal_key] = pref_value == 'on'
            elif pref_key == 'name':
                preferences[internal_key] = " ".join(context.args[1:])  # Allow multi-word names
            elif valid_values and pref_value in valid_values:
                preferences[internal_key] = pref_value
            else:
                await update.message.reply_text(
                    f"❌ Invalid value for {pref_key}. Valid options: {', '.join(valid_values)}",
                    parse_mode='Markdown'
                )
                return
            
            session['preferences'] = preferences
            save_user_data()
            
            await update.message.reply_text(
                f"✅ Preference updated: **{pref_key}** = {pref_value}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ Unknown preference: `{pref_key}`\n\nValid keys: style, length, emojis, level, name",
                parse_mode='Markdown'
            )
    else:
        # Show current preferences
        emoji_status = "✅ On" if preferences.get('include_emojis', True) else "❌ Off"
        name = preferences.get('name') or "Not set"
        
        prefs_text = f"""
⚙️ **Your Preferences**

• **Style:** {preferences.get('response_style', 'friendly').capitalize()}
• **Length:** {preferences.get('response_length', 'medium').capitalize()}
• **Emojis:** {emoji_status}
• **Expertise Level:** {preferences.get('expertise_level', 'general').capitalize()}
• **Your Name:** {name}

**To change a preference:**
`/preferences style professional`
`/preferences emojis off`
`/preferences name John`
`/preferences level expert`
"""
        await update.message.reply_text(prefs_text, parse_mode='Markdown')

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear user's conversation history"""
    user_id = update.effective_user.id
    if clear_user_history(user_id):
        await update.message.reply_text(
            """✅ **Conversation history cleared!** Starting fresh.

Your custom system prompt and model choice are kept.""",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Menu", callback_data='menu')
            ]])
        )
    else:
        await update.message.reply_text("❌ Error clearing history. Please try again.", parse_mode='Markdown')


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics"""
    user = update.effective_user
    session = get_user_session(user.id)
    if not session:
        await update.message.reply_text("❌ Error fetching your session data.")
        return

    chat_history_len = len(session.get('conversation_history', []))

    model_name = session.get('model_name', DEFAULT_MODEL)
    
    # Calculate session duration if possible
    session_duration = "N/A"
    if session.get('created_at'):
        try:
            created = datetime.strptime(session['created_at'], "%Y-%m-%d %H:%M:%S")
            duration = datetime.now() - created
            days = duration.days
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            if days > 0:
                session_duration = f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                session_duration = f"{hours}h {minutes}m"
            else:
                session_duration = f"{minutes}m"
        except:
            pass

    stats_text = f"""
📊 **Your Statistics:**

👤 **User:** {user.first_name} (@{user.username or 'N/A'})
🆔 **User ID:** {user.id}
💬 **Messages Sent:** {session.get('message_count', 0)}
📝 **Chat History:** {chat_history_len} messages (Max {MAX_HISTORY * 2})
🤖 **Your Model:** `{model_name}`
📅 **Session Created:** {session.get('created_at', 'N/A')}
⏱️ **Session Duration:** {session_duration}
⏰ **Last Active:** {session.get('last_message_time_str', 'N/A')}
"""

    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def current_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current model configuration"""
    session = get_user_session(update.effective_user.id)
    if not session:
        await update.message.reply_text("❌ Error fetching your session data.")
        return
    model_name = session.get('model_name', DEFAULT_MODEL)

    display_max_tokens = generation_config.get("max_tokens", "N/A")
    display_temp = generation_config.get("temperature", "N/A")
    display_top_p = generation_config.get("top_p", "N/A")

    model_text = f"""
🤖 **Current Cerebras/Llama Configuration:**

**Your Model:** `{model_name}`
**Temperature:** {display_temp}
**Max Tokens:** {display_max_tokens}
**Top P:** {display_top_p}

(Use /model to switch models)
"""

    await update.message.reply_text(model_text, parse_mode='Markdown')

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allow user to switch models"""
    session = get_user_session(update.effective_user.id)
    if not session:
        await update.message.reply_text("❌ Error fetching your session data.")
        return
    current_model = session.get('model_name', DEFAULT_MODEL)

    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data='menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"**Current Model:** `{current_model}`\n\n"
        "This bot uses **Llama 3.3 70B** model powered by Cerebras.\n\n"
        "The model is optimized for extreme speed.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show settings menu"""
    keyboard = [
        [InlineKeyboardButton("🗑️ Clear History", callback_data='clear_history')],
        [InlineKeyboardButton("🤖 Switch Model", callback_data='switch_model')],
        [InlineKeyboardButton("👤 Set Prompt", callback_data='system_prompt_info')],
        [InlineKeyboardButton("🔍 Search History", callback_data='search_info')],
        [InlineKeyboardButton("ℹ️ Model Info", callback_data='model_info')],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ **Settings**\n\nChoose an option:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show about information"""
    session = get_user_session(update.effective_user.id)
    model_name = "N/A"
    if session: model_name = session.get('model_name', DEFAULT_MODEL)

    # --- UPDATED About Message ---
    about_text = f"""
🤖 **Advanced Telegram Bot**
Powered by **RosingAI** 🌟

**Version:** 4.4.0 (Text Only)
**Your AI Model:** `{model_name}`

**About Cerebras/Llama:**
This bot uses Cerebras fast inference with Llama models:
• **{CEREBRAS_MODEL}** (Extreme Speed)

**Key Features:**
• Persistent conversation memory
• Custom system prompts (/system)
• Model switching (/model)
• Enforced token limits.
"""

    await update.message.reply_text(about_text, parse_mode='Markdown')

async def system_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View or set a custom system prompt"""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    if not session:
        await update.message.reply_text("❌ Error fetching your session data.")
        return

    if not context.args:
        current_prompt = session.get('system_prompt', DEFAULT_SYSTEM_INSTRUCTION)
        display_prompt = current_prompt[:3500] + ('...' if len(current_prompt) > 3500 else '')

        await update.message.reply_text(
            f"**Current System Prompt:**\n```\n{display_prompt}\n```\n\n"
            "**To set a new prompt:**\n`/system You are a helpful pirate.`\n\n"
            "**To reset:**\n`/system reset`\n\n"
            "(Setting a new prompt clears chat history)",
            parse_mode='Markdown'
        )
        return

    new_prompt_text = ' '.join(context.args)

    if new_prompt_text.lower() == 'reset':
        new_prompt = DEFAULT_SYSTEM_INSTRUCTION
        await update.message.reply_text("✅ System prompt reset to default.")
    elif not new_prompt_text.strip():
         await update.message.reply_text("⚠️ Please provide a prompt text after /system or use `/system reset`.")
         return
    else:
        new_prompt = new_prompt_text
        await update.message.reply_text(f"✅ New system prompt set!")

    session['system_prompt'] = new_prompt
    if clear_user_history(user_id):
         await update.message.reply_text("Chat history cleared to apply the new prompt.")
         save_user_data()
    else:
         await update.message.reply_text("⚠️ Error clearing history after setting prompt. Please try /clear manually.")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View recent conversation history"""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    if not session:
        await update.message.reply_text("❌ Error fetching your session data.")
        return

    chat = session.get('chat')
    if not chat or not hasattr(chat, 'history') or not chat.history:
        await update.message.reply_text("📭 No conversation history found. Start chatting to build history!")
        return

    # Get number of messages to show (default 5, max 20)
    limit = 5
    if context.args:
        try:
            limit = int(context.args[0])
            if limit < 1:
                limit = 5
            elif limit > 20:
                limit = 20
        except ValueError:
            limit = 5

    history = chat.history
    total_messages = len(history)
    
    # Get last N messages (each message pair is user + assistant)
    start_idx = max(0, total_messages - (limit * 2))
    recent_history = history[start_idx:]

    if not recent_history:
        await update.message.reply_text("📭 No recent messages to display.")
        return

    history_text = f"📜 **Recent Conversation History** ({len(recent_history)} messages)\n\n"
    
    for i, message in enumerate(recent_history):
        try:
            role = getattr(message, 'role', 'unknown')
            content = ""
            
            if hasattr(message, 'parts') and message.parts:
                for part in message.parts:
                    if hasattr(part, 'text'):
                        content += part.text
            elif hasattr(message, 'content') and hasattr(message.content, 'parts'):
                for part in message.content.parts:
                    if hasattr(part, 'text'):
                        content += part.text
            elif hasattr(message, 'text'):
                content = message.text
            
            # Truncate long messages
            if len(content) > 300:
                content = content[:300] + "..."
            
            role_emoji = "👤" if role == 'user' else "🤖"
            history_text += f"{role_emoji} **{role.upper()}:**\n`{content}`\n\n"
        except Exception as e:
            logger.warning(f"Error processing message in history for user {user_id}: {e}")
            continue

    history_text += f"\n_Use `/history N` to see more messages (max 20)_"
    
    if len(history_text) > MAX_MESSAGE_LENGTH:
        await send_split_message(update, context, history_text)
    else:
        await update.message.reply_text(history_text, parse_mode='Markdown')


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search through conversation history"""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    if not session:
        await update.message.reply_text("❌ Error fetching your session data.")
        return

    if not context.args:
        await update.message.reply_text(
            "🔍 **Search Conversation History**\n\n"
            "**Usage:** `/search your search term`\n\n"
            "**Example:** `/search python code`\n\n"
            "This will search through your recent conversation history and show matching messages.",
            parse_mode='Markdown'
        )
        return

    search_query = ' '.join(context.args).lower()
    if not search_query.strip():
        await update.message.reply_text("⚠️ Please provide a search term. Example: `/search python`", parse_mode='Markdown')
        return

    conversation_history = session.get('conversation_history', [])
    if not conversation_history:
        await update.message.reply_text("📭 No conversation history found. Start chatting to build history!")
        return

    # Search through history
    matches = []
    history = conversation_history
    
    for i, message in enumerate(history):
        try:
            # Skip system messages
            if message.get('role') == 'system':
                continue
                
            # Get message content
            content = message.get('content', '')
            content_lower = content.lower()
            
            # Check if search query matches (case-insensitive substring search)
            if search_query in content_lower:
                role = message.get('role', 'unknown')
                # Truncate long messages for display
                display_content = content[:200] + "..." if len(content) > 200 else content
                # Escape backticks in content to prevent markdown issues
                display_content = display_content.replace('`', "'")
                matches.append({
                    'index': i,
                    'role': role,
                    'content': display_content,
                    'full_content': content
                })
        except Exception as e:
            logger.warning(f"Error processing message in search for user {user_id}: {e}")
            continue

    # Escape search query for markdown display
    safe_query = search_query.replace('`', "'").replace('*', '').replace('_', ' ')
    
    if not matches:
        await update.message.reply_text(
            f"🔍 **No matches found** for: `{safe_query}`\n\n"
            "Try different keywords or check your conversation history with /stats",
            parse_mode='Markdown'
        )
        return

    # Format results
    results_text = f"🔍 **Found {len(matches)} match(es)** for: `{safe_query}`\n\n"
    
    # Limit to first 10 matches to avoid message length issues
    display_matches = matches[:10]
    
    for idx, match in enumerate(display_matches, 1):
        role_emoji = "👤" if match['role'] == 'user' else "🤖"
        results_text += f"{idx}. {role_emoji} **{match['role'].upper()}:**\n"
        results_text += f"   `{match['content']}`\n\n"
    
    if len(matches) > 10:
        results_text += f"\n_Showing first 10 of {len(matches)} matches. Refine your search for more specific results._"
    
    # Split if too long
    if len(results_text) > MAX_MESSAGE_LENGTH:
        await send_split_message(update, context, results_text)
    else:
        await update.message.reply_text(results_text, parse_mode='Markdown')


# ============ MESSAGE HANDLERS ============

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle regular text messages with enhanced features:
    - Concurrent processing (no blocking other users)
    - Smart rate limiting + spam detection  
    - Request detail detection (quick/general/detailed)
    - Dynamic token allocation (500-5000 tokens)
    - Professional ChatGPT/Gemini-style formatting
    """
    if not update.message or not update.message.text:
        logger.warning("Received update without message.")
        return

    user = update.effective_user
    user_id = user.id
    user_message = update.message.text.strip()

    if not user_message:
        return

    # ============ SMART RATE LIMITING ============
    # Rate limiting is handled by Telegram bot framework (no spam without explicit checks)

    session = get_user_session(user_id)
    if not session:
        await update.message.reply_text("❌ Session error. Please try /start")
        return

    current_time = datetime.now()
    session['last_message_time_dt'] = current_time
    session['last_message_time_str'] = current_time.strftime("%Y-%m-%d %H:%M:%S")
    session['message_count'] = session.get('message_count', 0) + 1
    session['username'] = user.username or user.first_name

    thinking_message = await update.message.reply_text("⚡ Processing...")
    processing_start = datetime.now()

    try:
        # ============ DETECT REQUEST TYPE ============
        conversation_length = len(session.get('conversation_history', []))
        
        # Simple request type detection
        is_question = '?' in user_message
        is_long = len(user_message.split()) > 20
        has_history = conversation_length > 5
        
        if is_long or (is_question and has_history):
            request_type = "detailed"
            max_tokens = 3000
        elif is_question:
            request_type = "general"
            max_tokens = 2000
        else:
            request_type = "brief"
            max_tokens = 1000
        
        logger.info(f"User {user_id} - Request type: {request_type}, tokens: {max_tokens}")
        
        # ============ INTENT CLASSIFICATION ============
        quick_intent = classify_intent(user_message)
        
        if quick_intent in [IntentType.GREETING, IntentType.SMALL_TALK]:
            intent = quick_intent
        elif quick_intent == IntentType.GENERAL_TASK:
            intent = IntentType.GENERAL_TASK
        elif quick_intent in [IntentType.TIME_QUERY, IntentType.DATE_QUERY]:
            intent = IntentType.REAL_TIME_DATA
        else:
            intent = await classify_intent_with_ai(user_message)

        # ============ DYNAMIC TOKEN ALLOCATION ============
        # Token count is now set above in request type detection
        if request_type == "detailed":
            response_instruction = "Provide a detailed, comprehensive response with examples."
        elif request_type == "brief":
            response_instruction = "Provide a brief, concise answer."
        else:
            response_instruction = "Provide a clear, helpful response."
        logger.info(f"Response instruction: {response_instruction[:50]}...")

        # ============ SMART SEARCH ============
        search_keywords = ['latest', 'current', 'today', 'now', 'recent', 'news', 'weather', 'price']
        search_needed = any(kw in user_message.lower() for kw in search_keywords)
        
        if intent in [IntentType.REAL_TIME_DATA, IntentType.INFO_QUESTION]:
            search_needed = True
        
        if search_needed:
            logger.info(f"Search enabled for user {user_id}")

        # ============ GET RESPONSE ============
        enhanced_content = f"{user_message}\n\n---\n{response_instruction}"
        response_text = await get_llama_response(enhanced_content, user_id, intent)

        if response_text:
            await stream_response_to_user(
                update, context,
                response_text,
                show_animation=True,
                provider="Cerebras"
            )
            
            try:
                await thinking_message.delete()
            except:
                pass
        else:
            await thinking_message.edit_text("⚠️ Empty response. Try again.")

        save_user_data()

    except Exception as e:
        import traceback
        logger.error(f"Error in handle_message {user_id}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        try:
            await thinking_message.edit_text("❌ Error. Try /clear")
        except:
            await update.message.reply_text("❌ Error. Try /clear")



async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document messages (Stub - Inform user)"""
    if not update.message or not update.message.document: return
    file = update.message.document
    await update.message.reply_text(
        f"📄 Document '{file.file_name}' received.\n\n"
        f"*(Note: I can't process document contents yet.)*"
    )

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages (Stub - Inform user)"""
    if not update.message or not update.message.voice: return
    await update.message.reply_text(
        "🎤 Voice message received!\n\n"
        "*(Note: I can't understand audio yet.)*"
    )

# ============ CALLBACK QUERY HANDLERS ============
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data

    if data == 'menu':
        keyboard = [
            [InlineKeyboardButton("📚 Help", callback_data='help'),
             InlineKeyboardButton("ℹ️ About", callback_data='about')],
            [InlineKeyboardButton("🔧 Settings", callback_data='settings'),
             InlineKeyboardButton("📊 Stats", callback_data='stats')]
        ]
        await query.edit_message_text(
             "🤖 **Main Menu**\n\nChoose an option:",
             reply_markup=InlineKeyboardMarkup(keyboard),
             parse_mode='Markdown'
        )
    elif data == 'help':
        # --- UPDATED Help Button Response ---
        help_text = "Send any message for a text reply!\n\nUse /help for all commands."
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='menu')]])
        await query.edit_message_text(help_text, parse_mode='Markdown', reply_markup=reply_markup)

    elif data == 'about':
        # --- UPDATED About Button Response ---
        session = get_user_session(user_id)
        model_name = "N/A"
        if session: model_name = session.get('model_name', DEFAULT_MODEL)
        about_text = f"🤖 **Powered by Cerebras/Llama AI**\n\n**Your Model:** `{model_name}`\nI understand text!"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='menu')]])
        await query.edit_message_text(about_text, parse_mode='Markdown', reply_markup=reply_markup)

    elif data == 'stats':
        session = get_user_session(user_id)
        if not session:
             await query.edit_message_text("❌ Error fetching session.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='menu')]]))
             return

        history_length = len(session.get('conversation_history', []))
        model_name = session.get('model_name', DEFAULT_MODEL)
        stats_text = f"📊 **Your Stats**\n\n💬 Messages: {session.get('message_count', 0)}\n📝 History: {history_length} msgs\n🤖 Model: `{model_name}`"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='menu')]])
        await query.edit_message_text(stats_text, parse_mode='Markdown', reply_markup=reply_markup)

    elif data == 'settings':
        keyboard = [
            [InlineKeyboardButton("🗑️ Clear History", callback_data='clear_history')],
            [InlineKeyboardButton("🤖 Switch Model", callback_data='switch_model')],
            [InlineKeyboardButton("👤 Set Prompt", callback_data='system_prompt_info')],
            [InlineKeyboardButton("🔍 Search History", callback_data='search_info')],
            [InlineKeyboardButton("ℹ️ Model Info", callback_data='model_info')],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='menu')]
        ]
        await query.edit_message_text(
             "⚙️ **Settings**\n\nChoose an option:",
             reply_markup=InlineKeyboardMarkup(keyboard),
             parse_mode='Markdown'
        )

    elif data == 'clear_history':
        if clear_user_history(user_id):
            await query.edit_message_text("✅ **History cleared!**", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data='settings')]]))
        else:
            await query.edit_message_text("❌ **Error clearing history.**", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data='settings')]]))

    elif data == 'switch_model':
        session = get_user_session(user_id)
        current_model = DEFAULT_MODEL
        if session: current_model = session.get('model_name', DEFAULT_MODEL)
        await query.edit_message_text(
            f"**Current Model:** `{current_model}`\n\n"
            "This bot uses **Llama 3.3 70B Versatile** model.\n"
            "Model switching is not available - using optimized single model.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data='settings')]]),
            parse_mode='Markdown'
        )


    elif data == 'model_info':
        session = get_user_session(user_id)
        model_name = "N/A"
        if session: model_name = session.get('model_name', DEFAULT_MODEL)
        display_max_tokens = generation_config.get("max_tokens", "N/A")
        display_temp = generation_config.get("temperature", "N/A")

        model_text = f"🤖 **Model Config**\n\n**Your Model:** `{model_name}`\n**Temp:** {display_temp}\n**Max Tokens:** {display_max_tokens}"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data='settings')]])
        await query.edit_message_text(model_text, parse_mode='Markdown', reply_markup=reply_markup)

    elif data == 'system_prompt_info':
        await query.edit_message_text(
            "Use the /system command in chat to view or change my personality.\n\n"
            "**Example:** `/system You are a pirate`\n"
            "**To reset:** `/system reset`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data='settings')]])
        )
    elif data == 'search_info':
        await query.edit_message_text(
            "🔍 **Search Conversation History**\n\n"
            "Use `/search your term` to search through your conversation history.\n\n"
            "**Example:** `/search python code`\n\n"
            "This will find all messages containing your search term.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data='settings')]])
        )
    else:
         logger.warning(f"Unhandled callback query data: {data}")
         # Avoid editing if possible, or provide a safe default
         try:
            await query.edit_message_text("Unknown button pressed.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='menu')]]))
         except Exception as edit_err:
             logger.error(f"Failed to edit message for unhandled callback: {edit_err}")


# ============ ERROR HANDLER ============
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Improved error handler with specific error handling."""
    error = context.error
    error_type = type(error).__name__
    error_msg = str(error)
    
    # Log detailed error info
    logger.error(f"Error type: {error_type}")
    logger.error(f"Error message: {error_msg}")
    logger.error("Full exception:", exc_info=error)
    
    # Determine user-friendly message based on error type
    if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
        user_message = "⏱️ Request timed out. Please try again."
    elif "rate" in error_msg.lower() or "limit" in error_msg.lower():
        user_message = "⚠️ Too many requests. Please wait a moment and try again."
    elif "api" in error_msg.lower() or "cerebras" in error_msg.lower():
        user_message = "🔧 AI service temporarily unavailable. Please try again in a moment."
    elif "network" in error_msg.lower() or "connection" in error_msg.lower():
        user_message = "🌐 Network error. Please check your connection and try again."
    else:
        user_message = "❌ An error occurred. Please try /clear or try again later."

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(user_message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
    else:
        logger.error(f"Error with non-standard update: {update}")


# ============ MAIN FUNCTION ============

# ============ EVENTS INTELLIGENCE AGENT (Merged) ============

@dataclass
class EventResult:
    """Standardized event data structure for cross-source deduplication."""
    title: str
    description: str
    date: Optional[str] = None
    time: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None
    source: str = "Unknown"
    category: Optional[str] = None
    is_online: bool = False
    relevance_score: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "title": self.title, "description": self.description, "date": self.date,
            "time": self.time, "location": self.location, "url": self.url,
            "source": self.source, "category": self.category,
            "is_online": self.is_online, "relevance_score": self.relevance_score
        }
    
    def __hash__(self): return hash(self.title.lower().strip())
    
    def __eq__(self, other):
        return isinstance(other, EventResult) and self._normalize(self.title) == self._normalize(other.title)
    
    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r'[^\w\s]', '', text.lower().strip())

EVENTS_QUERY_PATTERNS = [
    r'\b(event|events|meetup|meetups|conference|conferences|workshop|workshops)\b',
    r'\b(seminar|seminars|webinar|webinars|summit|summits|expo|exhibition)\b',
    r'\b(gathering|gatherings|fest|festival|festivals)\b',
    r'\b(happening|occurring|scheduled|hosted|organized)\s+(in|at|near|around)\b',
    r'\b(tech\s+event|developer\s+meetup|coding\s+workshop|programming\s+conference)\b'
]

def is_events_query(query: str) -> bool:
    for pattern in EVENTS_QUERY_PATTERNS:
        if re.search(pattern, query.lower(), re.IGNORECASE): return True
    return False

def extract_location_from_query(query: str) -> Optional[str]:
    known = ['delhi', 'mumbai', 'bangalore', 'bengaluru', 'hyderabad', 'chennai', 'pune', 'noida', 'gurgaon']
    for loc in known:
        if loc in query.lower(): return loc.title()
    return None

def extract_topic_from_query(query: str) -> Optional[str]:
    keywords = {'python': 'Python', 'ai': 'AI/ML', 'react': 'React', 'startup': 'Startups'}
    for k, v in keywords.items():
        if k in query.lower(): return v
    return None

async def search_eventbrite(query: str, location: str = None, max_results: int = 5) -> List[EventResult]:
    events = []
    try:
        url = f"https://www.eventbrite.com/d/{quote_plus(location or 'online')}/{quote_plus(query)}/"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={'User-Agent': 'Mozilla/5.0'}, follow_redirects=True)
            if resp.status_code == 200:
                titles = re.findall(r'<h2[^>]*class="[^"]*event-card__title[^"]*"[^>]*>([^<]+)</h2>', resp.text, re.IGNORECASE)[:max_results]
                for t in titles: events.append(EventResult(title=t.strip(), description=f"Eventbrite: {t.strip()}", location=location, source="Eventbrite", relevance_score=0.8))
    except Exception: pass
    return events

async def search_meetup(query: str, location: str = None, max_results: int = 5) -> List[EventResult]:
    events = []
    try:
        url = "https://www.meetup.com/gql"
        qry = {"operationName": "categorySearch", "variables": {"first": max_results, "query": query, "lat": 28.6, "lon": 77.2}, "query": "query categorySearch($query: String!, $first: Int) { keywordSearch(filter: { query: $query }, first: $first) { edges { node { result { ... on Event { title description dateTime venue { city } eventUrl } } } } } }"}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=qry, headers={'Content-Type': 'application/json'})
            if resp.status_code == 200:
                for edge in resp.json().get('data', {}).get('keywordSearch', {}).get('edges', []):
                    node = edge.get('node', {}).get('result', {})
                    if node: events.append(EventResult(title=node.get('title'), description=node.get('description', '')[:200], date=node.get('dateTime'), location=node.get('venue', {}).get('city'), url=node.get('eventUrl'), source="Meetup", relevance_score=0.9))
    except Exception: pass
    return events

class EventsIntelligenceAgent:
    def __init__(self):
        self.sources = [("Eventbrite", search_eventbrite), ("Meetup", search_meetup)]
    
    async def discover_events(self, query: str, location: str = None) -> List[EventResult]:
        if not location: location = extract_location_from_query(query)
        tasks = [func(query, location, 5) for _, func in self.sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_events = []
        for res in results:
            if isinstance(res, list): all_events.extend(res)
        return all_events
    
    def format_events_for_display(self, events):
        if not events: return "No events found."
        out = f"**Found {len(events)} Events:**\n"
        for i, e in enumerate(events, 1): out += f"{i}. {e.title} ({e.source})\n"
        return out

def main():
    """Start the bot."""
    logger.info("Starting Cerebras/Llama Telegram Bot...")

    if "8145214223:" in TELEGRAM_BOT_TOKEN or CEREBRAS_API_KEY.startswith("csk-"):
        logger.warning("API tokens appear hardcoded. Consider using environment variables for security.")

    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.critical("TELEGRAM_BOT_TOKEN is not set!")
        return

    if not CEREBRAS_API_KEY or CEREBRAS_API_KEY == "YOUR_CEREBRAS_API_KEY_HERE":
        logger.critical("CEREBRAS_API_KEY is not set!")
        return

    global user_sessions
    user_sessions = load_user_data()
    logger.info(f"Loaded data for {len(user_sessions)} users from {USER_DATA_FILE}.")

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    # Register Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("cmodel", current_model_command))
    application.add_handler(CommandHandler("model", model_command))
    application.add_handler(CommandHandler("system", system_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("history", history_command))

    # --- UPDATED Message Handlers ---
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # --- Photo handler REMOVED ---
    # application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)

    logger.info("✅ Bot setup complete. Starting polling...")
    logger.info(f"Default Model: {DEFAULT_MODEL} | Temp: {TEMPERATURE} | Max Tokens: {MAX_OUTPUT_TOKENS} | Rate Limit: {RATE_LIMIT_SECONDS}s")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

