#!/usr/bin/env python3
from datetime import datetime
from argparse import ArgumentParser
from sys import exit
from os import walk
from os.path import isfile, splitext, join, isdir
from subprocess import run
from json import loads
from collections import defaultdict
from uuid import uuid4
from colorlog import getLogger, StreamHandler, ColoredFormatter
from packaging.version import Version, parse

EXTs = ('mp4', 'mov', 'avi', 'jpg', 'jpeg', 'png', 'gif', 'tiff', 'tif', 'webp', 'heic', 'heif')

logger = getLogger(__name__)

def exif_tool(file_path: str, tags: list) -> dict[str, str]:
    cmd = ['exiftool', '-json', '-d', '%Y-%m-%dT%H:%M:%S%:z']
    cmd += [f'-{tag}' for tag in tags]
    cmd += [file_path]
    result = run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f'Error: Failed to extract metadata from {file_path}')
        exit(1)
    metadata = loads(result.stdout)[0]
    metadata.pop('SourceFile')
    return metadata

def get_track_creation_date(metadata: dict[str, str]) -> tuple[str|None, bool]:
    """Extract Media Create Date or Track Create Date from video tracks.
    Returns tuple of (date, was_found_in_track)
    """
    # Try Media Create Date first from any track
    for key in metadata:
        if 'MediaCreateDate' in key:
            return metadata[key], True
    # Fall back to Track Create Date from any track
    for key in metadata:
        if 'TrackCreateDate' in key:
            return metadata[key], True
    return None, False

def xmp(creation_date: datetime|None, content_id: str|None) -> str:
    result = "<?xpacket begin='\ufeff' id='W5M0MpCehiHzreSzNTczkc9d'?>\n" \
             "<x:xmpmeta xmlns:x='adobe:ns:meta/' x:xmptk='Image::ExifTool 12.99'>\n" \
             "<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>\n\n"
    
    if creation_date:
        result += "<rdf:Description rdf:about=''\n" \
                  " xmlns:exif='http://ns.adobe.com/exif/1.0/'>\n" \
                  f" <exif:DateTimeOriginal>{creation_date.isoformat()}</exif:DateTimeOriginal>\n" \
                  "</rdf:Description>\n\n" \
                  "<rdf:Description rdf:about=''\n" \
                  " xmlns:photoshop='http://ns.adobe.com/photoshop/1.0/'>\n" \
                  f" <photoshop:DateCreated>{creation_date.isoformat()}</photoshop:DateCreated>\n" \
                  "</rdf:Description>\n\n"
    if content_id:
        result += "<rdf:Description rdf:about=''\n" \
                  " xmlns:Apple='http://ns.exiftool.org/MakerNotes/Apple/1.0/'>\n" \
                  f" <Apple:ContentIdentifier>{content_id}</Apple:ContentIdentifier>\n" \
                  "</rdf:Description>\n\n"
    
    result += "</rdf:RDF>\n" \
              "</x:xmpmeta>\n" \
              "<?xpacket end='w'?>"

    return result

def main() -> None:

    parser = ArgumentParser(
                    description='This tool will create an XMP file for a given video file with the creation date of the video file.')
    parser.add_argument('dir', metavar='dir', type=str, help='The directory containing media files.')
    parser.add_argument('-f', '--force', action='store_true', help='Force the creation of XMP files even if they already exist.')
    parser.add_argument('-r', '--recalculate', action='store_true', help='Only regenerate XMP files for media that already has XMP files.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging.')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging.')
    args = parser.parse_args()

    handler = StreamHandler()
    handler.setFormatter(ColoredFormatter('%(log_color)s%(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel('DEBUG' if args.debug else 'INFO' if args.verbose else 'WARNING')

    result = run(['exiftool', '-ver'], capture_output=True, text=True)
    if result.returncode != 0:
        logger.error('exiftool is not available. Please install exiftool and try again.')
        exit(1)
    exiftool_ver = parse(result.stdout.strip())
    if exiftool_ver < Version('13.10'):
        logger.error(f'exiftool version 13.10 or newer is required ({exiftool_ver} installed). Please update exiftool and try again.')
        exit(1)
    
    if not isdir(args.dir):
        logger.error(f"Directory {args.dir} does not exist.")
        exit(1)

    file_paths = []
    for root, dirs, files in walk(args.dir):
        for file in files:
            if file.lower().endswith((EXTs)) and not file.startswith('._'):
                file_paths.append(join(root, file))
    file_paths.sort()

    file_pairs = defaultdict(list)
    for file_path in file_paths:
        root, ext = splitext(file_path)
        file_pairs[root].append(ext)

    processed_files = []
    for file, exts in file_pairs.items():
        if len(exts) == 2:
            logger.debug(f"Processing file pair: {file}")
            pair_creation_date = None
            pair_content_id = None
            skip = False
            from_track = False
            for ext in exts:
                file_path = f'{file}{ext}'
                metadata = exif_tool(file_path, ['EXIF:DateTimeOriginal', 'EXIF:CreateDate', 'XMP:DateCreated', 'XMP:CreateDate', 'MakerNotes:ContentIdentifier', 'Track*:MediaCreateDate', 'Track*:TrackCreateDate'])
                creation_date = metadata.get('DateTimeOriginal', metadata.get('CreateDate', metadata.get('DateCreated')))
                if not creation_date:
                    track_date, from_track = get_track_creation_date(metadata)
                    creation_date = track_date
                content_id = metadata.get('ContentIdentifier')
                if creation_date:
                    pair_creation_date = datetime.fromisoformat(creation_date)
                else:
                    logger.debug(f'No creation date in paired file {file_path}.')
                if content_id:
                    if pair_content_id and pair_content_id != content_id:
                        logger.warning(f'Content ID mismatch in {file_path}.')
                        skip = True
                        break
                    pair_content_id = content_id
                else:
                    if not pair_content_id:
                        logger.info(f'Creating Missing Content ID for {file_path}.')
                        pair_content_id = str(uuid4())
            if not skip:
                has_xmp = isfile(f'{file}{exts[0]}.xmp') or isfile(f'{file}{exts[1]}.xmp')
                should_process = args.force or (args.recalculate and has_xmp) or not has_xmp
                
                if not should_process:
                    logger.warning(f'XMP file already exists for pair {file}, skipping.')
                elif args.recalculate and not has_xmp:
                    logger.debug(f'Skipping pair {file} (no existing XMP file in recalculate mode).')
                else:
                    if from_track:
                        logger.info(f"Recovered creation date from track metadata for {file}")
                    for ext in exts:
                        with open(f'{file}{ext}.xmp', 'w') as f:
                            logger.info(f"Writing XMP Content ID {'& Date' if pair_creation_date else ''} file: {file}{ext}.xmp")
                            f.write(xmp(pair_creation_date, pair_content_id))
                        processed_files.append(f'{file}{ext}')

    for file_path in file_paths:
        if file_path not in processed_files:
            metadata = exif_tool(file_path, ['EXIF:DateTimeOriginal', 'EXIF:CreateDate', 'XMP:DateCreated', 'XMP:CreateDate', 'Track*:MediaCreateDate', 'Track*:TrackCreateDate'])
            creation_date = metadata.get('DateTimeOriginal', metadata.get('CreateDate', metadata.get('DateCreated')))
            from_track = False
            if not creation_date:
                track_date, from_track = get_track_creation_date(metadata)
                creation_date = track_date
            
            if creation_date:
                file_creation_date = datetime.fromisoformat(creation_date)
                root, ext = splitext(file_path)
                has_xmp = isfile(f'{file_path}.xmp')
                should_process = args.force or (args.recalculate and has_xmp) or not has_xmp
                
                if not should_process:
                    logger.warning(f'XMP file already exists for file {file_path}, skipping.')
                elif args.recalculate and not has_xmp:
                    logger.debug(f'Skipping {file_path} (no existing XMP file in recalculate mode).')
                else:
                    if from_track:
                        logger.info(f"Recovered creation date from track metadata for {file_path}")
                    with open(f'{file_path}.xmp', 'w') as f:
                        logger.info(f"Writing XMP Date file: {file_path}.xmp")
                        f.write(xmp(file_creation_date, None))
                    processed_files.append(file_path)
            else:
                logger.warning(f'No creation date found in {file_path}, skipping.')
    
    print(f"Complete.\nWrote {len(processed_files)} XMP files in {args.dir}.")

if __name__ == "__main__":
    main()