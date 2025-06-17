import json
import os
import random
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

form_data = {
    "SiteCompanyName1": None, "SiteAddress": None, "SiteCity": None, "SiteState": None, "SiteZip": None,
    "SiteVoice": None, "SiteFax": None, "CorporateCompanyName1": None, "CorporateAddress": None,
    "CorporateCity": None, "CorporateState": None, "CorporateZip": None, "CorporateName": None,
    "SiteEmail": None, "CorporateVoice": None, "CorporateFax": None, "BusinessWebsite": None,
    "CorporateEmail": None, "CustomerSvcEmail": None, "AppRetrievalMail": None, "AppRetrievalFax": None,
    "AppRetrievalFaxNumber": None, "MCC-Desc": None,

    # Simplified: use one initials and one signature field
    "MerchantInitials": None,
    "MerchantSignatureName": None
}

conversation_history = []
last_assistant_msg = ""
end_triggered = False
summary_given = False
summary_confirmed = False
pending_confirmation = None

CONFIRMATION_FIELDS = [
    "SiteCompanyName1", "CorporateCompanyName1", "CorporateName",
    "SiteEmail", "CorporateEmail", "CustomerSvcEmail",
    "SiteZip", "CorporateZip"
]

def get_initial_assistant_message():
    global last_assistant_msg
    greetings = [
        "Hi there! Ready to fill out your Merchant Application? Let's get started — what's your DBA or business name?",
        "Hello! I’ll be helping you fill out your merchant form. Let’s begin with your business’s DBA name.",
        "Welcome! Let’s kick things off. What’s the name your business operates under (DBA)?",
        "Hey! I’ll guide you through your Merchant form. First, can you tell me your DBA or business name?",
        "Great to have you! To start, what’s the doing-business-as (DBA) name for your company?"
    ]
    initial_message = random.choice(greetings)
    last_assistant_msg = initial_message
    conversation_history.append({
        "role": "assistant",
        "text": initial_message,
        "timestamp": datetime.now().isoformat()
    })
    return initial_message

def build_summary_from_form():
    summary_lines = []
    for field, value in form_data.items():
        if value:
            name = field.replace("MCC-Desc", "MCC SIC Description").replace("CustomerSvcEmail", "Customer Service Email")
            name = name.replace("SiteCompanyName1", "DBA Name").replace("CorporateCompanyName1", "Legal Corporate Name")
            name = name.replace("SiteAddress", "Business Address").replace("CorporateAddress", "Billing Address")
            name = name.replace("SiteVoice", "Phone").replace("SiteFax", "Fax")
            name = name.replace("SiteEmail", "Business Email")
            field_name = ' '.join([w.capitalize() for w in name.split()])
            summary_lines.append(f"{field_name}: {value}")
    summary = "\n\nHere is a summary of the information collected:\n\n" + "\n".join(summary_lines)
    summary += "\n\nPlease confirm if all the details are correct. Once confirmed, it may take a few seconds to process."
    return summary

async def process_transcribed_text(user_text):
    global last_assistant_msg, end_triggered, summary_given, summary_confirmed, pending_confirmation

    conversation_history.append({
        "role": "user",
        "text": user_text,
        "timestamp": datetime.now().isoformat()
    })

    if pending_confirmation:
        if any(kw in user_text.lower() for kw in ["yes", "correct", "confirmed", "that’s right"]):
            form_data[pending_confirmation[0]] = pending_confirmation[1]
            pending_confirmation = None
        else:
            clarification = f"Got it — let's try again. What should I note down for {pending_confirmation[0]}?"
            last_assistant_msg = clarification
            conversation_history.append({"role": "assistant", "text": clarification, "timestamp": datetime.now().isoformat()})
            return clarification

    extraction_prompt = f"""
You are helping fill out a Merchant Processing Application. Based on the assistant's last question and the user's reply, extract any relevant fields from this list:

{list(form_data.keys())}

Assistant: {last_assistant_msg}
User: {user_text}

Return only a JSON object using those exact field names. If unsure or likely to be wrong, still include it and indicate the confidence level like this:
{{ "SiteCompanyName1": {{"value": "Jane’s Burgers", "confidence": 0.6 }} }}

If nothing applies, return {{}}.
"""
    try:
        extract_response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You extract structured form fields with confidence."},
                {"role": "user", "content": extraction_prompt}
            ],
            temperature=0.3
        )
        extracted_json = json.loads(extract_response.choices[0].message.content.strip())
        for key, val in extracted_json.items():
            if key in form_data and form_data[key] is None:
                if isinstance(val, dict) and "value" in val:
                    if key in CONFIRMATION_FIELDS and val.get("confidence", 1) < 0.9:
                        guess = val["value"]
                        prompt = f"You said: {guess}. Did I get that right for {key}?"
                        pending_confirmation = (key, guess)
                        last_assistant_msg = prompt
                        conversation_history.append({"role": "assistant", "text": prompt, "timestamp": datetime.now().isoformat()})
                        return prompt
                    form_data[key] = val["value"]
                else:
                    form_data[key] = val
    except Exception as e:
        print("⚠️ Field extraction error:", e)

    core_fields = [k for k in form_data if k not in ("MerchantInitials", "MerchantSignatureName")]
    all_core_fields_filled = all(form_data[k] is not None for k in core_fields)

    if all_core_fields_filled and not summary_given:
        summary_given = True
        prompt = "Thanks! One last thing before we wrap up — could you give me your initials and your full name for the signature?"
        last_assistant_msg = prompt
        conversation_history.append({"role": "assistant", "text": prompt, "timestamp": datetime.now().isoformat()})
        return prompt

    if summary_given and not summary_confirmed:
        if any(phrase in user_text.lower() for phrase in ["yes", "correct", "confirmed", "looks good", "all good"]):
            summary_confirmed = True
            end_triggered = True
            final_msg = "END OF CONVERSATION"
            last_assistant_msg = final_msg
            conversation_history.append({"role": "assistant", "text": final_msg, "timestamp": datetime.now().isoformat()})
            return final_msg

    instruction_prompt = """
You are a conversational AI assistant helping users fill out a Merchant Processing Application.

Be intelligent, friendly, and natural—like Siri or ChatGPT. Guide the user through collecting the following fields only:

- DBAName
- LegalCorporateName
- BusinessAddress
- BillingAddress
- City
- State
- Zip
- Phone
- Fax
- ContactName
- BusinessEmail
- ContactPhone
- ContactFax
- ContactEmail
- Website
- CustomerServiceEmail
- RetrievalRequestDestination
- MCCSICDescription

Ask one or two natural, context-aware questions at a time. Provide gentle examples if needed. Avoid robotic phrasing.
Always prioritize privacy and remind the user not to share sensitive information unless necessary for the form. For sections requiring specific types of data like percentages, business types, or legal requirements, 
offer examples to aid in understanding.ONLY If the transcription is unclear or seems misspelled, spell it back to the user and ask for confirmation before moving on.NEVER include external links, promotional messages, or teaching tips.
Once all these fields are collected, read back the entire collected information to the user and ask them to confirm it and mention that it may take a few seconds to process all the information.
After they confirm, ask for initials and/or draw signature after conversation if missing. Then respond with 'END OF CONVERSATION' and nothing else.

DO NOT REPEAT THE SUMMARY. DO NOT REPEAT END OF CONVERSATION.
"""
    try:
        messages = [{"role": "system", "content": instruction_prompt}] + [
            {"role": msg["role"], "content": msg["text"]} for msg in conversation_history[-12:]
        ]
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.4
        )
        assistant_reply = response.choices[0].message.content.strip()

        if summary_given and ("summary" in assistant_reply.lower() or "end of conversation" in assistant_reply.lower()):
            return ""

        last_assistant_msg = assistant_reply
        conversation_history.append({"role": "assistant", "text": assistant_reply, "timestamp": datetime.now().isoformat()})
        return assistant_reply

    except Exception as e:
        print("❌ Assistant generation error:", e)
        return "Sorry, could you please repeat that?"

def reset_assistant_state():
    global conversation_history, last_assistant_msg, end_triggered, summary_given, summary_confirmed, pending_confirmation
    conversation_history.clear()
    last_assistant_msg = ""
    end_triggered = False
    summary_given = False
    summary_confirmed = False
    pending_confirmation = None
    for key in form_data:
        form_data[key] = None
