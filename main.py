#!/usr/bin/env python3

import argparse
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Tuple, Iterable
from PIL.Image import Image

import pypdfium2 as pdfium
from pypdfium2._helpers.misc import OptimiseMode


ORACLE_JVM_8 = '/usr/lib/jvm/java-8-oracle'
FIJI_IMAGEJ_EXECUTABLE = '/home/kinow/Downloads/Fiji.app/ImageJ-linux64'

logger = logging.getLogger(__name__)


class ExtractImagesFromPdfException(Exception):
    ...


class StitchImageException(Exception):
    ...


def main():
    parser = argparse.ArgumentParser(
        description='Converts a 2-page A4 document into a single page A3, stitching images that overlap.')
    parser.add_argument(dest='in_files', nargs='+', metavar='IN', type=str, help='Input PDF')
    parser.add_argument('--keep-files', action='store_true', help='Flag to keep intermediary files (left and right pages)')
    parser.add_argument('--debug', action='store_true', help='Log debug information')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    # Using the images produced by ImageJ's Extract from PDF plug-in results in
    # the wrong output for the Stitch plug-in. So we are using pypdfium2 to read
    # the PDF, and to export to image
    for in_file in args.in_files:
        try:
            left_page, left_page_name, right_page, right_page_name, output = extract_images_from_pdf(in_file)
            stitch_images(
                left_page=left_page,
                left_page_name=left_page_name,
                right_page=right_page,
                right_page_name=right_page_name,
                output=output,
                keep_files=args.keep_files)
        except ExtractImagesFromPdfException as e:
            logging.error(f'Failed to extract images from PDF {in_file}: {e}', e)
        except StitchImageException as e:
            logging.error(f'Failed to stitch images from PDF {in_file}: {e}', e)
        except Exception as e:
            logging.fatal(f'Unexpected error: {e}', e)


def extract_images_from_pdf(in_file: str, dpi: int = 300) -> Tuple[Image, str, Image, str, str]:
    """Extract the images from the PDF.

    It must contain two images. The second image must be rotated 180 degrees.

    The image file names returned are derived from the input file name, for
    example a file 131.pdf will produce 131-1.png (left), 131-2 (right), and
    131.png (final, stitched) images.

    Args:
        in_file (str): input file
        dpi (int): optional image quality
    Returns:
        Tuple[Image, str, Image, str, str]: A tuple with the left Pillow image, followed by
        the left image name, the right Pillow image, the right image name, and the
        destination file name
    """
    logger.info(f'Extracting images from {in_file}')
    with pdfium.PdfDocument(in_file) as pdf:
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

        in_file_stem = Path(in_file).stem
        left_page_name = f'{in_file_stem}-1.png'
        right_page_name = f'{in_file_stem}-2.png'
        output = f'{in_file_stem}.png'

        left_page.save(left_page_name)

        # When we scan an A3 document, in an A4 scanner, we get
        # two files of about the A4 size (scanner beds are larger
        # normally). The second A4 file will be inverted 180
        # degrees, so we need to rotate it here.
        right_page = right_page.rotate(180)
        right_page.save(right_page_name)
        right_page.close()

        logging.info(f'Created left page {left_page_name} and right page {right_page_name}')

        return left_page, left_page_name, right_page, right_page_name, output


def stitch_images(
        left_page: Image,
        left_page_name: str,
        right_page: Image,
        right_page_name: str,
        output: str,
        keep_files: bool = False):
    logging.info(f'Stitching image {left_page_name} with {right_page_name}, will save as {output}')
    imagej_macro = f'''open("{left_page_name}");
open("{right_page_name}");
selectWindow("{left_page_name}");
makeRectangle(2264, 0, 217, 3430);
open("{right_page_name}");
selectWindow("{right_page_name}");
makeRectangle(0, 30, 288, 3414);
run("Pairwise stitching", "first_image={left_page_name} second_image={right_page_name} fusion_method=[Linear Blending] fused_image={output} check_peaks=10 compute_overlap subpixel_accuracy x=2426.0000 y=-13.0000 registration_channel_image_1=[Average all channels] registration_channel_image_2=[Average all channels]");
saveAs("Png", "{output}");
print("Done.");
eval("script", "System.exit(0);");'''
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
        try:
            process = subprocess.Popen(
                command,
                env=env,
                stdout=sys.stdout,
                stderr=sys.stderr)
            process.wait()
        except Exception as e:
            raise StitchImageException(f'Failed to execute Fiji ImageJ macro command {command}: {e}', e)

    if not keep_files:
        logging.info(f'Deleting left page {left_page_name} and right page {right_page_name} images')
        Path(left_page_name).unlink()
        Path(right_page_name).unlink()


if __name__ == '__main__':
    main()
