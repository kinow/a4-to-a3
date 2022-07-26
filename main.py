#!/usr/bin/env python3

import argparse
import pypdfium2 as pdfium
from pypdfium2._helpers.misc import OptimiseMode
import stitching
import cv2
import numpy


def main():
    parser = argparse.ArgumentParser(description='Convert a 2-page A4 document to a single page A3')
    parser.add_argument('--in', dest='in_file', metavar='IN', type=str, required=True, help='Input PDF')
    args = parser.parse_args()

    # doc = pdfium.FPDF_LoadDocument(args.in_file, None)
    # page_count = pdfium.FPDF_GetPageCount(doc)
    # assert page_count == 2
    #
    # form_config = pdfium.FPDF_FORMFILLINFO(2)
    # form_fill = pdfium.FPDFDOC_InitFormFillEnvironment(doc, form_config)
    #
    # page = pdfium.FPDF_LoadPage(doc, 0)
    # width = math.ceil(pdfium.FPDF_GetPageWidthF(page))
    # height = math.ceil(pdfium.FPDF_GetPageHeightF(page))
    #
    # bitmap = pdfium.FPDFBitmap_Create(width, height, 0)
    # pdfium.FPDFBitmap_FillRect(bitmap, 0, 0, width, height, 0xFFFFFFFF)
    #
    # render_args = [bitmap, page, 0, 0, width, height, 0, pdfium.FPDF_LCD_TEXT | pdfium.FPDF_ANNOT]
    # pdfium.FPDF_RenderPageBitmap(*render_args)
    # pdfium.FPDF_FFLDraw(form_fill, *render_args)
    #
    # cbuffer = pdfium.FPDFBitmap_GetBuffer(bitmap)
    # buffer = ctypes.cast(cbuffer, ctypes.POINTER(ctypes.c_ubyte * (width * height * 4)))
    #
    # img = Image.frombuffer("RGBA", (width, height), buffer.contents, "raw", "BGRA", 0, 1)
    # img.save("out.png")
    #
    # pdfium.FPDFBitmap_Destroy(bitmap)
    # pdfium.FPDF_ClosePage(page)
    #
    # pdfium.FPDFDOC_ExitFormFillEnvironment(form_fill)
    # pdfium.FPDF_CloseDocument(doc)

    dpi = 300
    with pdfium.PdfDocument(args.in_file) as pdf:
        n_pages = len(pdf)
        if n_pages != 2:
            raise ValueError(f'Expected a 2-pages PDF, but got a {n_pages}-page(s) PDF.')

        page_indices = [i for i in range(n_pages)]
        renderer = pdf.render_topil(
            page_indices=page_indices,
            scale=dpi/72,  # https://github.com/pypdfium2-team/pypdfium2/issues/98
            optimise_mode=OptimiseMode.NONE,
        )

        # for image, index in zip(renderer, page_indices):
        #     image_filename = f'out_{str(index).zfill(n_pages)}.jpg'
        #     image.save(image_filename)
        #     image.close()

        images = list(renderer)
        page_1 = images[0]
        page_2 = images[1]

        page_1.save('out_1.png')
        page_2 = page_2.rotate(180)
        page_2.save('out_2.png')

        stitcher = cv2.Stitcher_create(mode=cv2.Stitcher_PANORAMA)
        stitcher.setPanoConfidenceThresh(0.1)
        opencv_page_1 = cv2.cvtColor(numpy.array(page_1), cv2.COLOR_RGB2BGR)
        opencv_page_2 = cv2.cvtColor(numpy.array(page_2), cv2.COLOR_RGB2BGR)

        status, result = stitcher.stitch([opencv_page_1, opencv_page_2])
        #  OK = 0,
        #  ERR_NEED_MORE_IMGS = 1,
        #  ERR_HOMOGRAPHY_EST_FAIL = 2,
        #  ERR_CAMERA_PARAMS_ADJUST_FAIL = 3
        if status != cv2.Stitcher_OK:
            raise ValueError("Can't stitch images, error code = %d" % status)
        cv2.imwrite("stitched.png", result)

        # settings = {"confidence_threshold": 0.2}
        # stitcher = stitching.Stitcher(**settings)
        # panorama = stitcher.stitch(['out_1.png', 'out_2.png'])
        # print(panorama)

        page_1.close()
        page_2.close()


if __name__ == '__main__':
    main()
