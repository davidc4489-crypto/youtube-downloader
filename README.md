# Youtube Downloader

Petite application de bureau Windows : collez le lien d'une video YouTube,
choisissez **MP3** (audio) ou **MP4** (video), et telechargez.

- Interface simple (tkinter), aucune installation requise : un seul `YoutubeDownloader.exe`
- ffmpeg est embarque dans l'exe (conversion MP3, fusion audio/video MP4)
- Choix du debit audio (128 / 192 / 320 kbps) ou de la resolution video (360p a 1080p / meilleure)
- Dossier de destination au choix (par defaut : `Telechargements`)

## Telecharger l'exe

L'exe est construit automatiquement par GitHub Actions a chaque push sur `main` :
onglet **Actions** > dernier run > artefact `YoutubeDownloader-windows`.
Un tag `vX.Y.Z` publie aussi une **Release** avec l'exe en piece jointe.

> Windows SmartScreen peut afficher un avertissement car l'exe n'est pas signe :
> cliquez sur « Informations complementaires » puis « Executer quand meme ».

## Construire soi-meme sous Windows

```bat
build_windows.bat
```

Le script cree un environnement virtuel, installe `yt-dlp`, `pyinstaller` et
`imageio-ffmpeg`, puis produit `dist\YoutubeDownloader.exe`.

## Lancer depuis les sources

```bash
pip install -r requirements.txt
python youtube_downloader.py
```

ffmpeg doit alors etre installe sur la machine (ou place a cote du script).

## Mise a jour de yt-dlp

YouTube change souvent : si les telechargements echouent, reconstruisez l'exe
pour embarquer la derniere version de `yt-dlp` (relancer le workflow suffit).
