#!/usr/bin/env python3

import argparse
import logging
import multiprocessing
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Tuple, Iterable, Union

import pypdfium2 as pdfium
import PIL
from PIL.Image import Image
from joblib import Parallel, delayed
from pypdfium2._helpers.misc import OptimiseMode

# NOTE: ImageJ needs an Oracle JVM 8, as it loads libs from a location that changed
#       after Java 8, and also uses Sun classes (removed from OpenJDK, Azul, etc.).
ORACLE_JVM_8 = '/usr/lib/jvm/java-8-oracle'
FIJI_IMAGEJ_EXECUTABLE = '/home/kinow/Downloads/Fiji.app/ImageJ-linux64'

OUTPUT_FILE_SIZE = 2000

logger = logging.getLogger(__name__)


class ExtractImagesFromPdfException(Exception):
    ...


class StitchImageException(Exception):
    ...


class AdjustLevelsException(Exception):
    ...


def main():
    """Application main method."""
    parser = argparse.ArgumentParser(
        description='Converts a 2-page A4 document into a single page A3, stitching images that overlap.')
    parser.add_argument(dest='in_files', nargs='+', metavar='IN', type=str, help='Input PDF')
    parser.add_argument('--keep-files', action='store_true',
                        help='Flag to keep intermediary files (left and right pages)')
    parser.add_argument('--debug', action='store_true', help='Log debug information')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    # Using the images produced by ImageJ's Extract from PDF plug-in results in
    # the wrong output for the Stitch plug-in. So we are using pypdfium2 to read
    # the PDF, and to export to image
    n_jobs = multiprocessing.cpu_count()
    n_jobs = min(n_jobs, len(args.in_files))
    if n_jobs > 1:
        n_jobs = n_jobs - 1
    logger.info(f"Running {n_jobs} jobs")
    Parallel(n_jobs=n_jobs, verbose=100)(delayed(process_pdf)(in_file, args.keep_files) for in_file in args.in_files)


def process_pdf(pdf_file: str, keep_files: bool = False) -> None:
    left_page: Union[Image, None] = None
    right_page: Union[Image, None] = None
    try:
        pdf_path = Path(pdf_file)
        left_page, left_page_path, right_page, right_page_path, output = extract_images_from_pdf(pdf_path)
        stitch_images(
            left_page=left_page,
            left_page_path=left_page_path,
            right_page=right_page,
            right_page_path=right_page_path,
            output=output,
            keep_files=keep_files)
        adjust_levels_resize(
            image=output
        )
    except ExtractImagesFromPdfException as e:
        logging.error(f'Failed to extract images from PDF {pdf_file}: {e}', e)
    except StitchImageException as e:
        logging.error(f'Failed to stitch images from PDF {pdf_file}: {e}', e)
    except Exception as e:
        logging.fatal(f'Unexpected error: {e}', e)
    finally:
        if left_page is not None:
            left_page.close()
        if right_page is not None:
            right_page.close()


def extract_images_from_pdf(in_file: Path, dpi: int = 300) -> Tuple[Image, Path, Image, Path, Path]:
    """Extract the images from the PDF.

    It must contain two images. The second image must be rotated 180 degrees.

    The image file names returned are derived from the input file name, for
    example a file 131.pdf will produce 131-1.png (left), 131-2 (right), and
    131.png (final, stitched) images.

    Args:
        in_file (Path): input file
        dpi (int): optional image quality
    Returns:
        Tuple[Image, Path, Image, Path, Path]: A tuple with the left Pillow image, followed by
        the left image, the right Pillow image, the right image, and the destination image
    """
    logger.info(f'Extracting images from {in_file}')
    with pdfium.PdfDocument(str(in_file.absolute())) as pdf:
        n_pages = len(pdf)
        if n_pages != 2:
            raise ExtractImagesFromPdfException(f'Expected a 2-pages PDF, but got a {n_pages}-page(s) PDF.')

        page_indices = [i for i in range(n_pages)]
        renderer: Iterable[Image] = pdf.render_topil(
            page_indices=page_indices,
            scale=dpi / 72,  # https://github.com/pypdfium2-team/pypdfium2/issues/98
            optimise_mode=OptimiseMode.NONE,
        )
        left_page: Image
        right_page: Image
        (left_page, right_page) = list(renderer)

        in_file_path = Path(in_file)
        in_file_stem = in_file_path.stem
        left_page_path = Path(in_file_path.parent) / f'{in_file_stem}-1.png'
        right_page_path = Path(in_file_path.parent) / f'{in_file_stem}-2.png'
        output = Path(in_file_path.parent) / f'{in_file_stem}.png'

        left_page.save(left_page_path)

        # When we scan an A3 document, in an A4 scanner, we get
        # two files of about the A4 size (scanner beds are larger
        # normally). The second A4 file will be inverted 180
        # degrees, so we need to rotate it here.
        right_page = right_page.rotate(180)
        right_page.save(right_page_path)
        right_page.close()

        logging.info(f'Created left page {left_page_path} and right page {right_page_path}')

        return left_page, left_page_path, right_page, right_page_path, output


def stitch_images(
        left_page: Image,
        left_page_path: Path,
        right_page: Image,
        right_page_path: Path,
        output: Path,
        keep_files: bool = False,
        threshold=0.1):
    logging.info(f'Stitching image {left_page_path} with {right_page_path}, will save as {output}')
    imagej_macro = f'''open("{left_page_path.absolute()}");
open("{right_page_path.absolute()}");
selectWindow("{left_page_path.name}");
run("Invert");
makeRectangle({left_page.width * (1.0 - threshold)}, 50, {threshold * left_page.width}, {left_page.height - 50});
selectWindow("{right_page_path.name}");
run("Invert");
makeRectangle(0, 50, {threshold * right_page.width}, {right_page.height - 50});
run("Pairwise stitching", "first_image={left_page_path.name} second_image={right_page_path.name} fusion_method=[Linear Blending] fused_image={output} check_peaks=10 compute_overlap subpixel_accuracy x=2426.0000 y=-13.0000 registration_channel_image_1=[Average all channels] registration_channel_image_2=[Average all channels]");
run("Invert");
saveAs("Png", "{output}");
print("Done.");
eval("script", "System.exit(0);");'''

    try:
        run_imagej_macro(imagej_macro)
    except Exception as e:
        raise StitchImageException(f'Failed to execute Fiji ImageJ macro: {e}', e)

    if not keep_files:
        logging.info(f'Deleting left page {left_page_path} and right page {right_page_path} images')
        left_page_path.unlink()
        right_page_path.unlink()


def adjust_levels_resize(image: Path) -> None:
    logging.info(f'Adjusting brightness and contrast')

    with PIL.Image.open(image.absolute()) as image_file:
        width = image_file.width
        height = image_file.height

    if width > OUTPUT_FILE_SIZE or height > OUTPUT_FILE_SIZE:
        biggest_side = OUTPUT_FILE_SIZE
        if width > height:
            ratio = OUTPUT_FILE_SIZE / width
        else:
            ratio = OUTPUT_FILE_SIZE / height
        width = width * ratio
        height = height * ratio
    else:
        biggest_side = width if width > height else height

    imagej_macro = f'''Color.setBackground("white");
    open("{image.absolute()}");
    selectWindow("{image.name}");
    run("Size...", "width={width} height={height} depth=1 constrain average interpolation=Bilinear");
    // run("Brightness/Contrast...");
    setMinAndMax(81, 252);
    saveAs("Png", "{image.absolute()}");
    run("Canvas Size...", "width={biggest_side} height={biggest_side} position=Center");
    saveAs("Png", "{image.parent / image.stem }-square.png");
    print("Done.");
    eval("script", "System.exit(0);");'''

    try:
        run_imagej_macro(imagej_macro)
    except Exception as e:
        raise AdjustLevelsException(f'Failed to execute Fiji ImageJ macro: {e}', e)


def run_imagej_macro(imagej_macro: str) -> None:
    logging.debug(f'Fiji ImageJ macro:\n{imagej_macro}')
    env = os.environ
    # NOTE: we need an Oracle JVM 8
    env['PATH'] = f'{ORACLE_JVM_8}/bin:' + env['PATH']
    logging.debug(f'New value for $PATH: {env["PATH"]}')

    with tempfile.NamedTemporaryFile() as nf:
        nf.write(imagej_macro.encode('UTF-8'))
        nf.flush()
        command = [
            FIJI_IMAGEJ_EXECUTABLE,
            '--ij2',
            '--headless',
            '--console',
            '-macro',
            nf.name]
        logging.debug(f'Executing Fiji ImageJ macro with command: {" ".join(command)}')
        process = subprocess.Popen(
            command,
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr)
        process.wait()


if __name__ == '__main__':
    main()
