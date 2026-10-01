"""Localized local fallback text with no configuration or network dependency."""

FALLBACK_MESSAGES = {
    "en": {
        "unclear": "I didn't quite get that, sorry. Could you repeat it again?",
        "safe": "I'm here to help. What would you like to know?",
        "blocked": "I can't help you with that. Ask me anything else.",
        "network": "I'm sorry, I can't respond right now. Please try again in a moment.",
    },
    "ar": {
        "unclear": "لم أفهمك جيدًا. هل يمكنك تكرار ذلك من فضلك؟",
        "safe": "أنا هنا للمساعدة. كيف يمكنني مساعدتك؟",
        "blocked": "لا أستطيع مساعدتك في ذلك. اسألني عن أي شيء آخر.",
        "network": "عذرًا، لا أستطيع الرد الآن. يرجى المحاولة مرة أخرى بعد قليل.",
    },
    "hi": {
        "unclear": "मैं आपको ठीक से समझ नहीं पाया। क्या आप दोबारा कह सकते हैं?",
        "safe": "मैं मदद के लिए यहाँ हूँ। मैं आपकी कैसे मदद कर सकता हूँ?",
        "blocked": "मैं इसमें आपकी मदद नहीं कर सकता। आप मुझसे कुछ और पूछ सकते हैं।",
        "network": "माफ़ कीजिए, मैं अभी जवाब नहीं दे सकता। कृपया थोड़ी देर बाद फिर कोशिश करें।",
    },
    "ur": {
        "unclear": "میں آپ کو ٹھیک سے سمجھ نہیں سکا۔ کیا آپ دوبارہ کہہ سکتے ہیں؟",
        "safe": "میں مدد کے لیے یہاں ہوں۔ میں آپ کی کیسے مدد کر سکتا ہوں؟",
        "blocked": "میں اس میں آپ کی مدد نہیں کر سکتا۔ آپ مجھ سے کچھ اور پوچھ سکتے ہیں۔",
        "network": "معذرت، میں ابھی جواب نہیں دے سکتا۔ براہ کرم تھوڑی دیر بعد دوبارہ کوشش کریں۔",
    },
    "fa": {
        "unclear": "خوب متوجه نشدم. می‌توانید دوباره تکرار کنید؟",
        "safe": "من برای کمک اینجا هستم. چه چیزی می‌خواهید بدانید؟",
        "blocked": "نمی‌توانم در این مورد کمک کنم. هر سؤال دیگری دارید بپرسید.",
        "network": "متأسفم، الان نمی‌توانم پاسخ بدهم. لطفاً کمی بعد دوباره تلاش کنید.",
    },
    "zh": {
        "unclear": "我没听清楚，抱歉。您能再说一遍吗？",
        "safe": "我随时为您提供帮助。您想了解什么？",
        "blocked": "我无法协助处理此事。您可以问我其他任何问题。",
        "network": "抱歉，我现在无法回答。请稍后再试。",
    },
}


def fallback_message(kind: str, language: str = "en") -> str:
    """Return a local fallback in the selected language when available."""
    code = language.lower().split("-")[0]
    return FALLBACK_MESSAGES.get(code, FALLBACK_MESSAGES["en"])[kind]


def specific_safety_refusal(transcript: str, language: str = "en") -> str | None:
    """Give a clear local refusal for common harmful how-to requests."""
    normalized = (transcript or "").casefold()
    code = language.lower().split("-")[0]
    if "hack" in normalized:
        replies = {
            "en": "I can't help with hacking.",
            "ar": "لا أستطيع المساعدة في الاختراق.",
            "hi": "मैं हैकिंग में मदद नहीं कर सकता।",
            "zh": "我不能帮助进行黑客攻击。",
        }
        return replies.get(code, replies["en"])
    if "weapon" in normalized or "make a bomb" in normalized:
        replies = {
            "en": "I can't help with instructions for making weapons.",
            "ar": "لا أستطيع المساعدة في تعليمات صنع الأسلحة.",
            "hi": "मैं हथियार बनाने के निर्देशों में मदद नहीं कर सकता।",
            "zh": "我不能帮助提供制作武器的说明。",
        }
        return replies.get(code, replies["en"])
    if "beat him up" in normalized or "beat her up" in normalized or "beat them up" in normalized:
        replies = {
            "en": "I can't help hurt someone. Take a moment away and talk it out calmly.",
            "ar": "لا أستطيع المساعدة في إيذاء شخص. خذ لحظة وناقش الأمر بهدوء.",
            "hi": "मैं किसी को चोट पहुँचाने में मदद नहीं कर सकता। थोड़ा रुकें और शांति से बात करें।",
            "zh": "我不能帮助伤害他人。请先冷静一下，再平和地沟通。",
        }
        return replies.get(code, replies["en"])
    return None
