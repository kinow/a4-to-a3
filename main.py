#!/usr/bin/env python3

import argparse
from pathlib import Path

import numpy
import pypdfium2 as pdfium
from pypdfium2._helpers.misc import OptimiseMode


def main():
    parser = argparse.ArgumentParser(description='Convert a 2-page A4 document to a single page A3')
    parser.add_argument('--in', dest='in_file', metavar='IN', type=str, required=True, help='Input PDF')
    args = parser.parse_args()

    # Using the images produced by ImageJ's Extract from PDF plug-in results in
    # the wrong output for the Stitch plug-in. So we are using pypdfium2 to read
    # the PDF, and to export to image
    images = extract_images_from_pdf(args.in_file)
    print(images)


def extract_images_from_pdf(in_file: str, dpi: int=300):
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

        left_page.save(left_page_name)
        left_page.close()

        # When we scan an A3 document, in an A4 scanner, we get
        # two files of about the A4 size (scanner beds are larger
        # normally). The second A4 file will be inverted 180
        # degrees, so we need to rotate it here.
        right_page = right_page.rotate(180)
        right_page.save(right_page_name)
        right_page.close()
        return (left_page_name, right_page_name)


def stitch_images(left_page, right_page):
    left_width, left_height = left_page.size
    right_width, right_height = right_page.size
    # 131.pdf has the same height
    # TODO: Work out when the images have different heights,
    #       choosing first the smallest, and the direction
    #       of the search; L-R, or R-L.
    # print(left_height, right_height)

    # TODO: Read one column of the right image.
    left_data = numpy.array(left_page)
    print(left_data)


if __name__ == '__main__':
    main()
