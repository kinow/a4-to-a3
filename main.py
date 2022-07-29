#!/usr/bin/env python3

import argparse
from pathlib import Path

import pypdfium2 as pdfium
from pypdfium2._helpers.misc import OptimiseMode

import subprocess, os, sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description='Convert a 2-page A4 document to a single page A3')
    parser.add_argument('--in', dest='in_file', metavar='IN', type=str, required=True, help='Input PDF')
    args = parser.parse_args()

    # Using the images produced by ImageJ's Extract from PDF plug-in results in
    # the wrong output for the Stitch plug-in. So we are using pypdfium2 to read
    # the PDF, and to export to image
    images = extract_images_from_pdf(args.in_file)
    print(images)
    stitch_images(*images)


def extract_images_from_pdf(in_file: str, dpi: int = 300):
    """Extract the images from the PDF.

    It must contain two images. The second image must be rotated 180 degrees.

    :in_file: input file
    :dpi: image quality
    """
    with pdfium.PdfDocument(in_file) as pdf:
        n_pages = len(pdf)
        if n_pages != 2:
            raise ValueError(f'Expected a 2-pages PDF, but got a {n_pages}-page(s) PDF.')

        page_indices = [i for i in range(n_pages)]
        renderer = pdf.render_topil(
            page_indices=page_indices,
            scale=dpi / 72,  # https://github.com/pypdfium2-team/pypdfium2/issues/98
            optimise_mode=OptimiseMode.NONE,
        )
        (left_page, right_page) = list(renderer)

        in_file_stem = Path(in_file).stem
        left_page_name = f'{in_file_stem}-1.png'
        right_page_name = f'{in_file_stem}-2.png'
        output = f'{in_file_stem}.png'

        left_page.save(left_page_name)
        left_page.close()

        # When we scan an A3 document, in an A4 scanner, we get
        # two files of about the A4 size (scanner beds are larger
        # normally). The second A4 file will be inverted 180
        # degrees, so we need to rotate it here.
        right_page = right_page.rotate(180)
        right_page.save(right_page_name)
        right_page.close()
        return (left_page_name, right_page_name, output)


def stitch_images(left_page, right_page, output):
    imagej_macro = f'''open("{left_page}");
open("{right_page}");
run("Pairwise stitching", "first_image={left_page} second_image={right_page} fusion_method=Median fused_image=131.png check_peaks=5 compute_overlap x=2426.0000 y=-13.0000 registration_channel_image_1=[Average all channels] registration_channel_image_2=[Average all channels]");
saveAs("Png", "{output}");
print("Done.");
eval("script", "System.exit(0);");'''

    env = os.environ
    # NOTE: we need an Oracle JVM 8
    env['PATH'] = '/usr/lib/jvm/java-8-oracle/bin:' + env['PATH']
    with tempfile.NamedTemporaryFile() as nf:
        nf.write(imagej_macro.encode('UTF-8'))
        nf.flush()
        command = [
            '/home/kinow/Downloads/Fiji.app/ImageJ-linux64',
            '--ij2',
            '--headless',
            '--console',
            '-macro',
            nf.name]
        process = subprocess.Popen(
            command,
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr)
        process.wait()

    Path(left_page).unlink()
    Path(right_page).unlink()


if __name__ == '__main__':
    main()
