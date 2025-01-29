locals {
  service_account_id = "ajedo4s1uf6ve4kcj6un"
  bucket = "tgbucket213124"
}

variable "cloud_id" {
  type = string
}

variable "folder_id" {
  type = string
}

terraform {
  required_providers {
    yandex = {
      source = "yandex-cloud/yandex"
    }
    telegram = {
      source = "yi-jiayu/telegram"
    }
  }
  required_version = ">= 0.13"
}

provider "yandex" {
  cloud_id                 = var.cloud_id
  folder_id                = var.folder_id
  service_account_key_file = pathexpand("~/keys/yc-key.json")
  zone                     = "ru-central1-d"
}

provider "telegram" {
  bot_token = var.tg_bot_key
}

resource "yandex_function_iam_binding" "cloud_func_publicity" {
  function_id = yandex_function.cloud_func.id
  role        = "serverless.functions.invoker"

  members = [
    "system:allUsers",
  ]
}

resource "yandex_function" "cloud_func" {
  name        = "func-homework-1"
  user_hash   = archive_file.code_zip.output_sha256
  runtime     = "python312"
  entrypoint  = "index.handler"
  memory      = 128
  execution_timeout  = "10"
  environment = { "TELEGRAM_BOT_TOKEN" = var.tg_bot_key, "SERVICE_ACCOUNT_API_KEY" = yandex_iam_service_account_api_key.sa_api_key.secret_key, "FOLDER_ID" = var.folder_id }
  content {
    zip_filename = archive_file.code_zip.output_path
  }
  service_account_id = local.service_account_id
  mounts {
    name = "mnt"
    mode = "rw"
    object_storage {
      bucket = yandex_storage_bucket.bucket.bucket
    }
  }
}

resource "archive_file" "code_zip" {
  type        = "zip"
  output_path = "func.zip"
  source_dir  = "src"
}

output "function_url" {
  value = "https://functions.yandexcloud.net/${yandex_function.cloud_func.id}"
}

variable "tg_bot_key" {
  type        = string
  description = "Telegram Bot Key"
  sensitive   = true
}

resource "telegram_bot_webhook" "tg_webhook" {
  url = "https://api.telegram.org/bot${var.tg_bot_key}/setWebhook?url=https://functions.yandexcloud.net/${yandex_function.cloud_func.id}"
}

resource "yandex_storage_bucket" "bucket" {
  bucket = local.bucket
}

resource "yandex_iam_service_account_api_key" "sa_api_key" {
  service_account_id = local.service_account_id
  description        = "this API-key is for my-robot"
}