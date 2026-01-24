# ============ ENHANCED RESPONSE SYSTEM ============
# Professional streaming animations + real-time text updates
# Matches ChatGPT/Claude aesthetic with multi-state progress indicators

import asyncio
import re
from enum import Enum
from datetime import datetime
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

class ProcessingState(Enum):
    """Define different processing states with emojis."""
    SEARCHING = ("🔍 Searching", "🌐 🔎 ⚙️ 🔍")
    ANALYZING = ("📊 Analyzing", "📈 📊 📉 📊")
    THINKING = ("💭 Thinking", "💭 🧠 💡 🧠")
    REASONING = ("📝 Reasoning", "⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏")
    GENERATING = ("⚡ Generating", "⚡ ✨ 💫 ⚡")

class ProgressIndicator:
    """Manages animated progress indicators for different states."""
    
    def __init__(self, state: ProcessingState, duration: float = 1.5):
        self.state = state
        self.duration = duration
        self.frames = state.value[1].split()
        self.description = state.value[0]
    
    def get_animation_frame(self, frame_index: int) -> str:
        """Get current animation frame."""
        return f"{self.frames[frame_index % len(self.frames)]} {self.description}"
    
    async def animate(self, update: Update, message_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Animate the progress indicator."""
        frame_index = 0
        start_time = datetime.now()
        
        while (datetime.now() - start_time).total_seconds() < self.duration:
            try:
                frame_text = self.get_animation_frame(frame_index)
                await context.bot.edit_message_text(
                    text=frame_text,
                    chat_id=update.effective_chat.id,
                    message_id=message_id
                )
                frame_index += 1
                await asyncio.sleep(0.25)  # 250ms per frame - faster
            except Exception as e:
                break

class StreamingAnimator:
    """Handles text streaming animations (word-by-word display)."""
    
    def __init__(self, update_interval: float = 0.6):
        self.update_interval = update_interval
    
    async def stream_text(self, update: Update, message_id: int, 
                         text: str, context: ContextTypes.DEFAULT_TYPE,
                         chunk_size: int = 75):
        """Stream text to user (chunk-based for efficiency)."""
        if not text:
            return
        
        # Split into chunks
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        full_text = ""
        
        for i, chunk in enumerate(chunks):
            full_text += chunk
            try:
                await context.bot.edit_message_text(
                    text=full_text,
                    chat_id=update.effective_chat.id,
                    message_id=message_id,
                    parse_mode='Markdown'
                )
                if i < len(chunks) - 1:  # Don't wait after last chunk
                    await asyncio.sleep(self.update_interval)
            except Exception as e:
                # Message too frequent or other error, just continue
                continue

class StreamingResponseFormatter:
    """Formats responses with professional markdown styling."""
    
    @staticmethod
    def format_with_sections(response: str, title: str = None) -> str:
        """Add professional formatting to response."""
        if title:
            return f"**{title}**\n\n{response}"
        return response
    
    @staticmethod
    def format_with_code_blocks(response: str) -> str:
        """Wrap code sections in proper markdown."""
        # If response contains code patterns, wrap in backticks
        if '```' not in response and ('{' in response or 'def ' in response or 'function' in response):
            lines = response.split('\n')
            formatted = []
            in_code = False
            for line in lines:
                if any(keyword in line for keyword in ['def ', 'class ', 'function', 'const ', 'var ']):
                    if not in_code:
                        formatted.append('```python')
                        in_code = True
                    formatted.append(line)
                elif in_code and line.strip() == '':
                    formatted.append('```')
                    in_code = False
                    formatted.append(line)
                else:
                    formatted.append(line)
            if in_code:
                formatted.append('```')
            return '\n'.join(formatted)
        return response
    
    @staticmethod
    def add_metadata(response: str, provider: str = "AI", duration: float = None) -> str:
        """Add metadata footer."""
        metadata = f"\n\n⚡ {provider}"
        if duration:
            metadata += f" | ⏱️ {duration:.2f}s"
        return response + metadata

class ProfessionalResponseBuilder:
    """Builds complete response with multiple components."""
    
    def __init__(self):
        self.progress_states = [
            (ProcessingState.SEARCHING, 1.5),
            (ProcessingState.ANALYZING, 1.2),
            (ProcessingState.THINKING, 1.3),
            (ProcessingState.REASONING, 1.5),
            (ProcessingState.GENERATING, 0.8)
        ]
    
    async def stream_response_to_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                     response_text: str, show_animation: bool = True,
                                     provider: str = "Cerebras") -> None:
        """Main entry point: shows progress then streams response."""
        start_time = datetime.now()
        
        # Step 1: Send initial "thinking" message
        thinking_message = await update.message.reply_text("🤔 Processing...")
        
        if show_animation:
            # Step 2: Show progress states
            for state, duration in self.progress_states:
                indicator = ProgressIndicator(state, duration)
                await indicator.animate(update, thinking_message.message_id, context)
        
        # Step 3: Stream the actual response
        animator = StreamingAnimator(update_interval=0.6)
        formatter = StreamingResponseFormatter()
        
        # Format response
        formatted_response = formatter.format_with_sections(response_text)
        
        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()
        
        # Add metadata
        final_response = formatter.add_metadata(formatted_response, provider, duration)
        
        # Stream it
        await animator.stream_text(update, thinking_message.message_id, final_response, context)

# Create global instance
response_builder = ProfessionalResponseBuilder()

async def stream_response_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                 response_text: str, show_animation: bool = True,
                                 provider: str = "Cerebras") -> None:
    """Convenience function to use the response builder."""
    await response_builder.stream_response_to_user(
        update, context, response_text, show_animation, provider
    )
