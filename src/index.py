import json
from base64 import b64encode
import requests
import os
from pathlib import Path

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
TELEGRAM_FILE_URL = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"
FOLDER_ID = os.environ.get("FOLDER_ID")
MOUNT = os.environ.get("MOUNT")
BUCKET_OBJECT_KEY = os.environ.get("BUCKET_OBJECT_KEY")

BAD_MESSAGE_TEXT = "Я не смог подготовить ответ на экзаменационный вопрос."
TEXT_OR_PHOTO_TEXT = "Я могу обработать только текстовое сообщение или фотографию."
HELP_TEXT = "Я помогу подготовить ответ на экзаменационный вопрос по дисциплине 'Операционные системы'. Пришлите мне фотографию с вопросом или наберите его текстом."

def _text_message(text, message, iam_token):
    answer = get_answer(text, iam_token)
    send_message(BAD_MESSAGE_TEXT if not answer else answer, message)
    
def send_message(reply_text, input_message):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    data = {
        "chat_id": input_message["chat"]["id"],
        "text": reply_text,
        "reply_parameters": {
            "message_id": input_message["message_id"]
        }
    }

    requests.post(url=url, json=data)

def get_file_path(file_id):
    url = f"{TELEGRAM_API_URL}/getFile"
    data = { "file_id": file_id }
    response = requests.get(url=url, params=data)

    return None if response.status_code != 200 else response.json()["result"].get("file_path")

def get_image(file_path):
    url = f"{TELEGRAM_FILE_URL}/{file_path}"
    response = requests.get(url=url)

    return None if response.status_code != 200 else response.content

def get_answer(question, iam_token):
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {iam_token}"
    }
    data = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt",
        "messages": [
            {"role": "system", "text": _get_data_from_bucket()},
            {"role": "user", "text": question}
        ]
    }
    response = requests.post(url=url, headers=headers, json=data)

    if response.status_code != 200:
        return None

    alternatives = response.json()["result"]["alternatives"]
    final_alternatives = list(filter(
        lambda alternative: alternative["status"] == "ALTERNATIVE_STATUS_FINAL",
        alternatives
    ))

    return None if not final_alternatives else final_alternatives[0]["message"].get("text")

def handler(event, context):
    try:
        if event is None or "body" not in event:
            print(event)
            print(context)
            return {"statusCode": 400, "body": "Invalid event"}
        
        update = json.loads(event["body"])

    except TypeError as e:
        return {"statusCode": 500, "body": str(e)}
    message = update.get("message")

    if message:
        _message(message, context.token["access_token"])

    return { "statusCode": 200 }

def _message(message, iam_token):
    if (text := message.get("text")) and text in {"/start", "/help"}:
        send_message(HELP_TEXT, message)
    elif text := message.get("text"):
        _text_message(text, message, iam_token)
    elif image := message.get("photo"):
        _photo_message(image, message, iam_token)
    else:
        send_message(TEXT_OR_PHOTO_TEXT, message)

def _photo_message(tg_photo, message, iam_token):
    image_path = get_file_path(tg_photo[-1]["file_id"])
    image = get_image(image_path)
    text = recognize_text(b64encode(image).decode("utf-8"), iam_token)

    send_message(BAD_MESSAGE_TEXT, message) if not text else _text_message(text, message, iam_token)


def recognize_text(base64_image, iam_token):
    url = "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {iam_token}",
    }
    data = {
        "content": base64_image,
        "mimeType": "image/jpeg",
        "languageCodes": ["ru", "en"],
    }

    response = requests.post(url=url, headers=headers, json=data)
    if response.status_code != 200:
        return None

    text = response.json()["result"]["textAnnotation"]["fullText"].replace("-\n", "").replace("\n", " ")

    return None if not text else text

def _get_data_from_bucket():
    with open(Path("/function/storage", MOUNT, BUCKET_OBJECT_KEY), "r") as file:
        data = file.read()
    return data
