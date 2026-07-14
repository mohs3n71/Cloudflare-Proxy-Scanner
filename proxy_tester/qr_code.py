class QrCodeUnavailableError(RuntimeError):
    pass


def build_qr_matrix(value):
    try:
        import qrcode
    except ImportError as exc:
        raise QrCodeUnavailableError(
            "QR code support is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=4,
    )
    qr.add_data(value)
    qr.make(fit=True)
    return qr.get_matrix()


def qr_canvas_layout(matrix, canvas_size):
    if not matrix or not matrix[0]:
        raise ValueError("QR matrix cannot be empty.")
    module_count = len(matrix)
    if any(len(row) != module_count for row in matrix):
        raise ValueError("QR matrix must be square.")
    module_size = max(1, canvas_size // module_count)
    rendered_size = module_size * module_count
    offset = (canvas_size - rendered_size) // 2
    return module_size, offset
