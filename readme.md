# Ukay-Ukay Marketplace & Styling Platform

[![Django](https://img.shields.io/badge/Django-4.2-brightgreen)](https://www.djangoproject.com/)
[![PWA](https://img.shields.io/badge/PWA-Compatible-blue)](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

A sustainable fashion marketplace with virtual styling capabilities, promoting ethical consumption through second-hand clothing trade.

![Project Screenshot](static/images/screenshot.png)

## Features
- 🛍️ Second-hand clothing marketplace
- 👗 Virtual mix-and-match styling tool
- 📱 Progressive Web App (PWA) support
- 🔍 Advanced filtering and search
- 📸 Image scanning and processing
- 💬 Social sharing capabilities

## Installation

### Prerequisites
- Python 3.9+
- pip
- Virtual Environment (recommended)

### Setup Instructions

1. **Clone Repository**
   ```bash
   git clone https://github.com/LamberlainMuli/csci42
   cd csci42
   ```
2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/MacOS
   venv\Scripts\activate  # Windows
   ```
3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Environment Configuration**
   Create a `.env` file in the project root:
   ```bash
   echo "DEBUG=True" >> .env
   echo "SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')" >> .env
   ```
5. **Database Setup**
   ```bash
   python manage.py migrate
   ```
6. **Create Superuser (Optional)**
   ```bash
   python manage.py createsuperuser
   ```
7. **Run Development Server**
   ```bash
   python manage.py runserver
   ```
8. Visit http://localhost:8000 in your browser.

## Usage

### Basic Commands
- Start development server:
  ```bash
  python manage.py runserver
  ```
- Create new migrations:
  ```bash
  python manage.py makemigrations
  ```
- Apply migrations:
  ```bash
  python manage.py migrate
  ```
- Access admin panel: http://localhost:8000/admin


## Configuration
Update these in `.env` file:

```ini
DEBUG=True
SECRET_KEY=your-generated-secret-key
```


## License
Distributed under the MIT License. See `LICENSE` for more information.

## Acknowledgements
Development Team
- Kyla Ysabelle Apolinario
- Kristine Nicole Banzon
- Lamberlain Muli
- Maria Charmane Rose Naciongayo
- Roxanne Silvallana
