#!/usr/bin/env python3

import argparse
import requests
import os
import sys
import json
import getpass
import logging
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def print_help():
    print("""
Использование: script.py [options]

Обязательные аргументы:
  --hive HIVE             Адрес Hive (например, http://127.0.0.1)
  --screenshots PATH      Путь к папке со скриншотами Gowitness
  --jsonl FILE            Путь к файлу в формате JSONL Gowitness

Необязательные аргументы:
  --login                 Аутентификация в Hive
  --debug                 Включить отладочные сообщения
  --help                  Показать это сообщение и выйти
  --projectid PROJECTID   ID проекта в Hive
""")

def create_session_with_retries():
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "PATCH"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def authenticate(hive_url, save_session):
    login = input("Введите логин: ")
    password = getpass.getpass("Введите пароль: ")
    mfa = ''
    mfa_input = input("Ввести MFA? Y/N: ").strip().lower()
    if mfa_input == 'y':
        mfa = input("Введите MFA токен: ")

    auth_data = {
        "userLogin": login,
        "userPassword": password,
        "mfaToken": mfa
    }

    session = create_session_with_retries()
    logging.debug(f"Отправка запроса аутентификации на {hive_url}/api/session с данными {auth_data}")
    try:
        response = session.post(f"{hive_url}/api/session", json=auth_data)
        logging.debug(f"Код ответа аутентификации: {response.status_code}, текст ответа: {response.text}")
        if response.status_code == 200:
            print("Аутентификация успешна.")
            if save_session:
                with open('session.cookie', 'w') as f:
                    f.write(session.cookies.get('BSESSIONID', ''))
            return session
        else:
            print("Ошибка аутентификации.")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        logging.error(f"Сетевая ошибка при аутентификации: {e}")
        sys.exit(1)

def load_session(hive_url):
    session = create_session_with_retries()
    if os.path.exists('session.cookie'):
        with open('session.cookie', 'r') as f:
            bsessionid = f.read().strip()
            session.cookies.set('BSESSIONID', bsessionid)
            logging.debug(f"Загружена сессия с BSESSIONID: {bsessionid}")
    else:
        print("Файл session.cookie не найден. Пожалуйста, выполните аутентификацию с помощью опции --login.")
        sys.exit(1)
    return session

def get_projects(session, hive_url):
    try:
        response = session.get(f"{hive_url}/api/project/editable/")
        logging.debug(f"Получение списка проектов, код ответа: {response.status_code}, текст ответа: {response.text}")
        if response.status_code == 200:
            projects = response.json()
            return projects
        elif response.status_code == 401:
            print("Необходима аутентификация. Пожалуйста, выполните команду с опцией '--login'.")
            sys.exit(1)
        else:
            print("Ошибка при получении списка проектов.")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        logging.error(f"Сетевая ошибка при получении проектов: {e}")
        sys.exit(1)

def select_project(projects):
    print("Выберите проект для загрузки данных:")
    for idx, project in enumerate(projects, start=1):
        project_path = ['/' if part == 'default' else part for part in project['projectPath']]
        path_str = ' - '.join(project_path + [project['projectName']])
        print(f"{idx}. - {path_str}")
    choice = input("Введите номер проекта: ").strip()
    if not choice.isdigit():
        print("Неверный выбор.")
        sys.exit(1)
    choice = int(choice) - 1
    if 0 <= choice < len(projects):
        return projects[choice]['projectId']
    else:
        print("Неверный выбор.")
        sys.exit(1)

def parse_jsonl(jsonl_file):
    data = []
    with open(jsonl_file, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    data.append({
                        'url': entry.get('url', ''),
                        'final_url': entry.get('final_url', ''),
                        'response_code': entry.get('response_code', ''),
                        'protocol': entry.get('protocol', ''),
                        'file_name': entry.get('file_name', '')
                    })
                except json.JSONDecodeError as e:
                    logging.error(f"Ошибка разбора JSON строки: {e}")
    logging.debug(f"Разобрано {len(data)} записей из JSONL файла.")
    return data

def search_asset(session, hive_url, projectid, search_string):
    url = f"{hive_url}/api/project/{projectid}/graph/search"
    logging.debug(f"Поиск актива с запросом: {search_string}")
    try:
        response = session.post(url, json={"searchString": search_string})
        logging.debug(f"Код ответа: {response.status_code}, текст ответа: {response.text}")
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            print("Необходима аутентификация. Пожалуйста, выполните команду с опцией '--login'.")
            sys.exit(1)
        else:
            print("Ошибка при поиске актива.")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        logging.error(f"Сетевая ошибка при поиске актива: {e}")
        sys.exit(1)

def create_asset(session, hive_url, projectid, asset_data):
    url = f"{hive_url}/api/project/{projectid}/graph/nodes"
    logging.debug(f"Создание актива с данными: {asset_data}")
    try:
        response = session.post(url, json=[asset_data])
        logging.debug(f"Код ответа: {response.status_code}, текст ответа: {response.text}")
        if response.status_code == 200:
            return response.json()[0]  # Возвращаем созданный актив
        else:
            print("Ошибка при создании актива.")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        logging.error(f"Сетевая ошибка при создании актива: {e}")
        sys.exit(1)

def upload_file(session, hive_url, projectid, nodeId, file_path, caption='Gowitness', filename='image.jpeg'):
    url = f"{hive_url}/api/project/{projectid}/graph/file_node"
    logging.debug(f"Загрузка файла {file_path} на узел {nodeId}")
    try:
        with open(file_path, 'rb') as f:
            files = {
                'file': (filename, f, 'image/jpeg'),
            }
            data = {
                'caption': caption,
                'filename': filename,
                'nodeId': str(nodeId)
            }
            response = session.post(url, files=files, data=data)
        logging.debug(f"Код ответа: {response.status_code}, текст ответа: {response.text}")
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            print("Необходима аутентификация. Пожалуйста, выполните команду с опцией '--login'.")
            sys.exit(1)
        else:
            print("Ошибка при загрузке файла.")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        logging.error(f"Сетевая ошибка при загрузке файла: {e}")
        sys.exit(1)
    except FileNotFoundError:
        logging.error(f"Файл {file_path} не найден.")
        sys.exit(1)

def update_note_patch(session, hive_url, projectid, note_id, text):
    url = f"{hive_url}/api/project/{projectid}/graph/nodes/{note_id}"
    data = {
        'text': text
    }
    logging.debug(f"Обновление заметки {note_id} на узле {url} с текстом: {text}")
    try:
        response = session.patch(url, json=data)
        logging.debug(f"Код ответа: {response.status_code}, текст ответа: {response.text}")
        if response.status_code == 200:
            return True
        elif response.status_code == 401:
            print("Необходима аутентификация. Пожалуйста, выполните команду с опцией '--login'.")
            sys.exit(1)
        else:
            print("Ошибка при обновлении заметки.")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        logging.error(f"Сетевая ошибка при обновлении заметки: {e}")
        sys.exit(1)

def create_note(session, hive_url, projectid, nodeId, text):
    url = f"{hive_url}/api/project/{projectid}/graph/nodes"
    data = [{
        'nodeId': nodeId,
        'text': text
    }]
    logging.debug(f"Создание заметки на узле {nodeId} с текстом: {text}")
    try:
        response = session.post(url, json=data)
        logging.debug(f"Код ответа: {response.status_code}, текст ответа: {response.text}")
        if response.status_code == 200:
            return True
        elif response.status_code == 401:
            print("Необходима аутентификация. Пожалуйста, выполните команду с опцией '--login'.")
            sys.exit(1)
        else:
            print("Ошибка при создании заметки.")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        logging.error(f"Сетевая ошибка при создании заметки: {e}")
        sys.exit(1)

def get_note_text(session, hive_url, projectid, note_id):
    url = f"{hive_url}/api/project/{projectid}/graph/nodes/{note_id}"
    logging.debug(f"Получение текста заметки {note_id}")
    try:
        response = session.get(url)
        logging.debug(f"Код ответа: {response.status_code}, текст ответа: {response.text}")
        if response.status_code == 200:
            return response.json().get('text', '')
        elif response.status_code == 401:
            print("Необходима аутентификация. Пожалуйста, выполните команду с опцией '--login'.")
            sys.exit(1)
        else:
            print("Ошибка при получении текста заметки.")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        logging.error(f"Сетевая ошибка при получении текста заметки: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--hive', required=True, help='Адрес Hive (например, http://127.0.0.1)')
    parser.add_argument('--projectid', help='ID проекта в Hive')
    parser.add_argument('--screenshots', required=True, help='Путь к папке со скриншотами')
    parser.add_argument('--jsonl', required=True, help='Путь к файлу в формате JSONL')
    parser.add_argument('--login', action='store_true', help='Аутентификация в Hive')
    parser.add_argument('--debug', action='store_true', help='Включить отладочные сообщения')
    parser.add_argument('--help', action='store_true', help='Показать справку и выйти')

    args = parser.parse_args()

    if args.help:
        print_help()
        sys.exit(0)

    # Настройка логирования
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s')

    hive_url = args.hive.rstrip('/')

    # Аутентификация
    if args.login:
        save_session_input = input("Сохранить сессию в файл? Y/N: ").strip().lower()
        save_session = True if save_session_input == 'y' else False
        session = authenticate(hive_url, save_session)
    else:
        session = load_session(hive_url)

    # Получение projectid
    if not args.projectid:
        projects = get_projects(session, hive_url)
        projectid = select_project(projects)
    else:
        projectid = args.projectid

    # Парсинг JSONL файла
    entries = parse_jsonl(args.jsonl)

    for entry in entries:
        url = entry['url']
        final_url = entry['final_url']
        response_code = entry['response_code']
        protocol = entry['protocol']
        file_name = entry['file_name']
        # Получение домена или IP
        parsed_url = urlparse(url)
        netloc = parsed_url.hostname
        if not netloc:
            netloc = parsed_url.path  # Если urlparse не смог распарсить
        logging.debug(f"Обработанный netloc: {netloc}")
        is_ip = netloc.replace('.', '').isdigit()
        if is_ip:
            search_string = f"ip == {netloc}"
        else:
            search_string = f'hostname == "{netloc}"'
        # Поиск актива
        assets = search_asset(session, hive_url, projectid, search_string)
        if not assets:
            print(f"Актив {netloc} не найден. Создаю новый актив.")
            # Создаем актив
            if is_ip:
                asset_data = {"ip": netloc}
            else:
                asset_data = {"hostname": netloc}
            asset = create_asset(session, hive_url, projectid, asset_data)
            # Получаем nodeId
            nodeId = asset.get('id')
            notes = []
            gowitness_note = None
        else:
            asset = assets[0]
            if is_ip:
                nodeId = asset.get('id')
            else:
                hostnames = asset.get('hostnames', [])
                if hostnames:
                    nodeId = hostnames[0].get('id')
                else:
                    logging.error(f"Не удалось получить id из hostnames для актива {netloc}.")
                    continue
            notes = asset.get('notes', [])
            gowitness_note = None
            for note in notes:
                if 'Gowitness' in note.get('text', '') and url in note.get('text', ''):
                    gowitness_note = note
                    break
        # Загрузка файла
        file_path = os.path.join(args.screenshots, file_name)
        if not os.path.exists(file_path):
            logging.error(f"Файл {file_path} не найден.")
            continue
        file_info = upload_file(session, hive_url, projectid, nodeId, file_path)
        file_uuid = file_info.get('uuid')
        # Формирование текста заметки
        img_src = f"/api/project/{projectid}/graph/file/{file_uuid}"
        details_text = (
            f"<details>\n"
            f"<summary>Gowitness {url}</summary><br>\n"
            f"<h5>Final Url: </h5><a href={final_url}>{final_url}</a><br>\n"
            f"<h5>Response code: </h5>{response_code}<br>\n"
            f"<h5>Protocol: </h5>{protocol}<br>\n"
            f"<img src=\"{img_src}\"></img>\n"
            f"</details>"
        )
        if gowitness_note:
            # Обновление существующей заметки
            note_id = gowitness_note.get('id')
            previous_text = get_note_text(session, hive_url, projectid, note_id)
            new_text = f"{previous_text}\n{details_text}"
            update_note_patch(session, hive_url, projectid, note_id, new_text)
        else:
            # Создание новой заметки
            create_note(session, hive_url, projectid, nodeId, details_text)

if __name__ == '__main__':
    main()
