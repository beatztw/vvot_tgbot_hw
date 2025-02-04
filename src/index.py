import json
from base64 import b64encode
import requests
import os
import telebot
import boto3
from pathlib import Path

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
vision_url = 'https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText'
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
TELEGRAM_FILE_URL = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"
FOLDER_ID = os.environ.get("FOLDER_ID")
BUCKET_NAME = os.environ.get("BUCKET_NAME")
BUCKET_OBJECT_KEY = os.environ.get("BUCKET_OBJECT_KEY")
folder_id = ""
iam_token = ''

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False)
BAD_MESSAGE_TEXT = "Я не смог подготовить ответ на экзаменационный вопрос."
TEXT_OR_PHOTO_TEXT = "Я могу обработать только текстовое сообщение или фотографию."
HELP_TEXT = "Я помогу подготовить ответ на экзаменационный вопрос по дисциплине 'Операционные системы'. Пришлите мне фотографию с вопросом или наберите его текстом."

s3 = boto3.client(
    "s3",
    endpoint_url="https://storage.yandexcloud.net",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, HELP_TEXT)

@bot.message_handler(func=lambda message: True, content_types=['photo'])
def echo_photo(message):
    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    image_data = b64encode(downloaded_file).decode('utf-8')
    response_text = image_analyze(vision_url, iam_token, folder_id, image_data)

    bot.send_message(message.chat.id, "Распознанный текст: \n" + response_text)
    res = BAD_MESSAGE_TEXT if not response_text else answer_from_gpt(message, response_text)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def echo_message(message):
    answer_from_gpt(message, message.text)

@bot.message_handler(func=lambda message: True, content_types=['voice'])
def echo_audio(message):
    bot.reply_to(message, TEXT_OR_PHOTO_TEXT)

def image_analyze(vision_url, iam_token, folder_id, image_data):
    response = requests.post(vision_url, headers={'Authorization': 'Bearer '+iam_token, 'x-folder-id': folder_id}, json={
        "mimeType": "image",
        "languageCodes": ["en", "ru"],
        "model": "page",
        "content": image_data
        })
    blocks = response.json()['result']['textAnnotation']['blocks']
    text = ''
    for block in blocks:
        for line in block['lines']:
            for word in line['words']:
                text += word['text'] + ' '
            text += '\n'
    return text

def process_event(event):
    try:
        update = telebot.types.Update.de_json(event['body'])
        bot.process_new_updates([update])
        return {"statusCode": 200, "body": "OK"}
    except Exception as e:
        print(f"Ошибка: {e}")
        return {"statusCode": 500, "body": "Error"}

# Получение идентификатора каталога
def get_folder_id(iam_token, version_id):

    headers = {'Authorization': f'Bearer {iam_token}'}
    function_id_req = requests.get(f'https://serverless-functions.api.cloud.yandex.net/functions/v1/versions/{version_id}',
                                   headers=headers)
    function_id_data = function_id_req.json()
    function_id = function_id_data['functionId']
    folder_id_req = requests.get(f'https://serverless-functions.api.cloud.yandex.net/functions/v1/functions/{function_id}',
                                 headers=headers)
    folder_id_data = folder_id_req.json()
    folder_id = folder_id_data['folderId']
    return folder_id

def handler(event, context):
    global iam_token, folder_id
    process_event(event)
    iam_token = context.token["access_token"]
    version_id = context.function_version
    folder_id = get_folder_id(iam_token, version_id)

    return { "statusCode": 200}
    
def get_instruction_from_bucket():
    get_object_response = s3.get_object(Bucket=BUCKET_NAME, Key=BUCKET_OBJECT_KEY)
    return get_object_response['Body'].read().decode('utf8')

def answer_from_gpt(message, question):
    print("iam_token2 - "+ iam_token)
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    model_url = "gpt://"+FOLDER_ID+"/yandexgpt"
    data = {
        "modelUri": model_url,
        "completionOptions": {
        "stream": False,
        "temperature": 0.6,
        "maxTokens": "2000"
        },
        "messages": [
            {
                "role": "system", 
                "text": get_instruction_from_bucket()
            },
            {
                "role": "user", 
                "text": question
            }
        ]
    }
    
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {iam_token}', 'x-folder-id': FOLDER_ID}

    response = requests.post(url=url, headers=headers, json=data)
    
    alternatives = response.json()["result"]["alternatives"]
    alternatives_status_final = list(filter(lambda alternative: alternative["status"] == "ALTERNATIVE_STATUS_FINAL",alternatives))

    result = BAD_MESSAGE_TEXT if not alternatives_status_final else alternatives_status_final[0]["message"].get("text")

    bot.reply_to(message, result)

    return result

bot.polling()