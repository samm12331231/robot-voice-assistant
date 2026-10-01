# Manual language-routing smoke prompts

Run these in text mode only. The expected detection column describes the
assistant's routing result; uncertain means the assistant should use the
current session language or configured default rather than a detector guess.

| # | Prompt | Expected detected language | Expected reply language |
|---:|---|---|---|
| 1 | Where does Drake live? | English | English |
| 2 | Can you tell me a joke? | English | English |
| 3 | What's the weather there? | English | English |
| 4 | I didn't like that joke. Say another joke. | English | English |
| 5 | We're talking about Dubai right now. | English | English |
| 6 | Could you explain that again? | English | English |
| 7 | Yes. | Current session language (English after an English turn) | English |
| 8 | Okay. | Current session language (English after an English turn) | English |
| 9 | Thank you. | Current session language (English after an English turn) | English |
| 10 | Hola, hola. | Spanish | Spanish |
| 11 | Bonjour, comment ça va ? | French | French |
| 12 | Waar woon Drake? | Afrikaans | Afrikaans |
| 13 | مرحبا، كيف حالك؟ | Arabic | Arabic |
| 14 | halo | Uncertain (use current/default language) | Current/default language |
| 15 | ہیلو ہیلو | Uncertain (use current/default language) | Current/default language |

The final two greetings are intentionally ambiguous. Confirm that they do not
switch the remembered session language based on a one-word detector guess.
