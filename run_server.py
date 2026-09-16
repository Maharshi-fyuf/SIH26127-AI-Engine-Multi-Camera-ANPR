import os
import uvicorn

if __name__ == '__main__':
    if os.getenv('YUVATECH_AUTO_DOWNLOAD_MODELS','false').lower() in {'1','true','yes','on'}:
        from scripts.bootstrap_models import download
        download(['plate','helmet','seatbelt'], os.getenv('YUVATECH_MODEL_CACHE','models'))
    uvicorn.run('api.server:app', host='0.0.0.0', port=8000, reload=False)
