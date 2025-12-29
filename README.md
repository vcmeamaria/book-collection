#  Maria’s Library

This is a local web tool to catalogue and organise a personal book collection.  
It runs entirely on your own machine.

---

## ▶️ How to run it locally

To run the tool locally, make sure you do the following:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn jinja2 python-multipart
uvicorn app:app --reload 

browser:
http://127.0.0.1:8000/home
http://127.0.0.1:8000/add
http://127.0.0.1:8000/collection
