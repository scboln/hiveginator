# HiveGINaToR
Hive Gowitness Integration

Скрипт позволяет загрузить результаты Gowitness 3 в Hive от Hexway

#### Gowitness scan
Для запуска нам потребуются результаты Gowitness 3 
```bash
gowitness scan file -f hosts.txt --write-db --write-jsonl
```
Выполнение этой команды создаст скриншоты, sqlite базу данных и jsonl файл результатов с именем gowitness.jsonl

#### Запуск hiveginator.py

Загрузка с github
```bash
git clone https://github.com/scboln/hiveginator.git
```

Запуск

```bash
cd hiveginator && chmod +x hiveginator.py
```
Запуск для логина и получения Cookie ```--login```, будет предложено сохранить сессионную Cookie для дальнейшей работы
```bash
./hiveginator.py --hive http://hive_ip --screenshots ../gowitness/screenshots --jsonl ../gowitness/gowitness.jsonl --login
```

если не указан аргумент:
```--projectid``` будет предложен выбор проекта для загрузки
