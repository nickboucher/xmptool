#!/usr/bin/env python3
from datetime import datetime
from argparse import ArgumentParser
from sys import exit
from os import walk, remove
from os.path import isfile, splitext, join, isdir, basename
from glob import glob
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

def get_creation_date(metadata: dict[str, str]) -> tuple[str|None, bool]:
    """Extract creation date from metadata, trying standard fields first, then track-level fields.
    Returns tuple of (date, was_found_in_track)
    """
    # Try standard EXIF/XMP dates first
    creation_date = metadata.get('DateTimeOriginal', metadata.get('CreateDate', metadata.get('DateCreated')))
    if creation_date:
        return creation_date, False
    
    # Fall back to Media Create Date
    if 'MediaCreateDate' in metadata:
        return metadata['MediaCreateDate'], True
    # Fall back to Track Create Date
    if 'TrackCreateDate' in metadata:
        return metadata['TrackCreateDate'], True
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
                    description='This tool creates XMP sidecar files to link Live Photos and optionally expose datetime metadata.',
                    epilog='Note: At least one of -l/--live-photos or -t/--time must be specified.')
    parser.add_argument('path', metavar='path', type=str, help='Directory, single file, or glob pattern containing media files.')
    parser.add_argument('-f', '--force', action='store_true', help='Force the creation of XMP files even if they already exist.')
    parser.add_argument('-r', '--recalculate', action='store_true', help='Only regenerate XMP files for media that already has XMP files.')

    # Group the flags that are required as "at least one must be present" so help shows them together
    req_group = parser.add_argument_group('required options', 'At least one of the following must be specified')
    req_group.add_argument('-t', '--time', action='store_true', dest='time', help='Process datetime metadata. (At least one of -l/--live-photos or -t/--time is required.)')
    req_group.add_argument('-l', '--live-photos', action='store_true', dest='live_photos', help='Process Live Photo content IDs (linking images to their corresponding videos). (At least one of -l/--live-photos or -t/--time is required.)')

    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging.')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging.')
    args = parser.parse_args()

    # Require at least one of --time or --live-photos
    if not (args.time or args.live_photos):
        parser.error('At least one of -l/--live-photos or -t/--time must be specified.')

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
    
    # Accept a directory, a single file, or a glob pattern
    file_paths = []
    if isdir(args.path):
        for root, dirs, files in walk(args.path):
            for file in files:
                if file.lower().endswith((EXTs)) and not file.startswith('._'):
                    file_paths.append(join(root, file))
    elif isfile(args.path):
        # Single file
        if args.path.lower().endswith(EXTs) and not basename(args.path).startswith('._'):
            file_paths = [args.path]
        else:
            logger.error(f"File {args.path} is not a supported media file.")
            exit(1)
    else:
        # Treat as glob pattern
        matches = glob(args.path, recursive=True)
        for m in matches:
            if isfile(m) and m.lower().endswith(EXTs) and not basename(m).startswith('._'):
                file_paths.append(m)
        if not file_paths:
            logger.error(f'No media files found for pattern: {args.path}')
            exit(1)
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
            
            # Build tag list based on flags
            tags = []
            if args.live_photos:
                tags.append('MakerNotes:ContentIdentifier')
            if args.time:
                tags.extend(['EXIF:DateTimeOriginal', 'EXIF:CreateDate', 'XMP:DateCreated', 'XMP:CreateDate', 'MediaCreateDate', 'TrackCreateDate'])
            
            for ext in exts:
                file_path = f'{file}{ext}'
                metadata = exif_tool(file_path, tags)
                
                # Only process datetime if --time flag is passed
                if args.time:
                    creation_date, from_track = get_creation_date(metadata)
                    if creation_date:
                        try:
                            pair_creation_date = datetime.fromisoformat(creation_date)
                        except ValueError:
                            logger.warning(f'Invalid creation date format "{creation_date}" in {file_path}, skipping date.')
                            pair_creation_date = None
                    else:
                        logger.debug(f'No creation date in paired file {file_path}.')

                # Only process ContentIdentifier if live photos flag is passed
                if args.live_photos:
                    content_id = metadata.get('ContentIdentifier')
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
                
                # Determine if we would write an XMP file (consider both live-photo content ID and datetime flags)
                would_write_xmp = (args.live_photos and pair_content_id is not None) or (args.time and pair_creation_date is not None)
                
                # If in force or recalculate mode and we wouldn't write an XMP, delete existing ones
                if (args.force or args.recalculate) and has_xmp and not would_write_xmp:
                    for ext in exts:
                        xmp_path = f'{file}{ext}.xmp'
                        if isfile(xmp_path):
                            logger.info(f'Deleting XMP file that would not be recreated: {xmp_path}')
                            remove(xmp_path)
                elif not should_process:
                    logger.warning(f'XMP file already exists for pair {file}, skipping.')
                elif args.recalculate and not has_xmp:
                    logger.debug(f'Skipping pair {file} (no existing XMP file in recalculate mode).')
                elif would_write_xmp:
                    if from_track and args.time:
                        logger.info(f"Recovered creation date from track metadata for {file}")
                    for ext in exts:
                        with open(f'{file}{ext}.xmp', 'w') as f:
                            logger.info(f"Writing XMP Content ID {'& Date' if pair_creation_date else ''} file: {file}{ext}.xmp")
                            f.write(xmp(pair_creation_date, pair_content_id if args.live_photos else None))
                        processed_files.append(f'{file}{ext}')

    # Process single files (non-Live Photos) if --time flag is passed
    if args.time:
        for file_path in file_paths:
            if file_path not in processed_files:
                metadata = exif_tool(file_path, ['EXIF:DateTimeOriginal', 'EXIF:CreateDate', 'XMP:DateCreated', 'XMP:CreateDate', 'MediaCreateDate', 'TrackCreateDate'])
                creation_date, from_track = get_creation_date(metadata)
                
                if creation_date:
                    try:
                        file_creation_date = datetime.fromisoformat(creation_date)
                    except ValueError:
                        logger.warning(f'Invalid creation date format "{creation_date}" in {file_path}, skipping.')
                        continue
                    
                    root, ext = splitext(file_path)
                    has_xmp = isfile(f'{file_path}.xmp')
                    should_process = args.force or (args.recalculate and has_xmp) or not has_xmp
                    
                    # If in force or recalculate mode and we have no datetime, delete existing XMP
                    if (args.force or args.recalculate) and has_xmp and not creation_date:
                        logger.info(f'Deleting XMP file that would not be recreated: {file_path}.xmp')
                        remove(f'{file_path}.xmp')
                    elif not should_process:
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
                    # No creation date found - delete existing XMP if in force/recalculate mode
                    has_xmp = isfile(f'{file_path}.xmp')
                    if (args.force or args.recalculate) and has_xmp:
                        logger.info(f'Deleting XMP file for file with no creation date: {file_path}.xmp')
                        remove(f'{file_path}.xmp')
                    else:
                        logger.warning(f'No creation date found in {file_path}, skipping.')
    else:
        # If --time is NOT passed, delete XMP files for single files in force/recalculate mode
        # since single files would not be processed without --time
        if args.force or args.recalculate:
            for file_path in file_paths:
                if file_path not in processed_files:
                    xmp_path = f'{file_path}.xmp'
                    if isfile(xmp_path):
                        logger.info(f'Deleting XMP file for single file (--time not passed): {xmp_path}')
                        remove(xmp_path)
    
    print(f"Complete.\nWrote {len(processed_files)} XMP files for {args.path}.")

if __name__ == "__main__":
    main()