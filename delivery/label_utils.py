"""
Utility functions for generating shipping labels when orders are published to delivery tasks.
"""
import uuid
import logging
from io import BytesIO
from django.core.files import File
from django.utils import timezone

logger = logging.getLogger(__name__)


def generate_label_number(order, delivery_task):
    """Generate a unique label number based on order and task info.

    The order number already opens with the client's business code
    (MVA124-5850-AB785), so prefixing it again only made the id longer to read
    with no extra information: LBL-MVA124-MVA124-5850-AB785-DCD323.
    """
    short_uuid = str(uuid.uuid4()).replace('-', '').upper()[:6]
    return f"LBL-{order.order_number}-{short_uuid}"


def generate_barcode_image(barcode_data):
    """Generate a barcode image from the given data"""
    import barcode
    from barcode.writer import ImageWriter

    try:
        EAN = barcode.get_barcode_class('code128')
        ean = EAN(barcode_data, writer=ImageWriter())
        buffer = BytesIO()
        ean.write(buffer)
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"Error generating barcode: {str(e)}")
        return None


def generate_barcode_svg(barcode_data, quiet_zone=10, bar_height=100):
    """
    Build a Code128 barcode as inline SVG markup that stretches to its container.

    A rasterised barcode (generate_barcode_image) gets resampled by the browser
    when it is scaled to the label width, which greys out the bar edges — on a
    203dpi thermal head that is the difference between a scan and a no-read.
    This emits one <rect> per bar in a unitless viewBox with
    preserveAspectRatio="none" + shape-rendering="crispEdges", so the printer
    rasterises the bars itself at its own resolution with hard edges.

    quiet_zone is in modules (Code128 needs >= 10 of blank on each side).
    Returns an SVG string, or '' if the data cannot be encoded.
    """
    from html import escape

    from barcode.codex import Code128

    try:
        modules = Code128(str(barcode_data)).build()[0]
    except Exception as e:
        logger.error(f"Error generating barcode SVG: {str(e)}")
        return ''

    total = len(modules) + (quiet_zone * 2)
    rects = []
    x = quiet_zone
    run_start = None
    for i, module in enumerate(modules):
        if module == '1':
            if run_start is None:
                run_start = x + i
        elif run_start is not None:
            rects.append(f'<rect x="{run_start}" y="0" width="{x + i - run_start}" height="{bar_height}"/>')
            run_start = None
    if run_start is not None:
        rects.append(f'<rect x="{run_start}" y="0" width="{x + len(modules) - run_start}" height="{bar_height}"/>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} {bar_height}" '
        f'preserveAspectRatio="none" shape-rendering="crispEdges" '
        f'role="img" aria-label="{escape(str(barcode_data), quote=True)}">'
        f'<rect x="0" y="0" width="{total}" height="{bar_height}" fill="#fff"/>'
        f'<g fill="#000">{"".join(rects)}</g>'
        f'</svg>'
    )


def generate_qr_svg(data, border=2, error_correction='M'):
    """
    Build a QR code as inline SVG markup — the scannable code on the waybill.

    Code128 lost the parcels: stretched to the label width it ends up around a
    pixel per module, which a phone camera cannot resolve, and a 1D code also
    has to be held straight and close. A QR carries the same order number in a
    square a driver can scan from any angle, tolerates ink smudge through its
    error correction, and stays readable at 20mm.

    Emitted as one <rect> per run of dark modules in a unitless viewBox with
    shape-rendering="crispEdges", so the printer rasterises it at its own
    resolution instead of resampling a PNG. The default aspect ratio is kept —
    a stretched QR does not scan.

    `border` is the quiet zone in modules (the spec asks for 4; 2 is the floor
    that still reads and buys space on a 58mm roll).
    Returns an SVG string, or '' if the data cannot be encoded.
    """
    from html import escape

    import qrcode

    levels = {
        'L': qrcode.constants.ERROR_CORRECT_L,
        'M': qrcode.constants.ERROR_CORRECT_M,
        'Q': qrcode.constants.ERROR_CORRECT_Q,
        'H': qrcode.constants.ERROR_CORRECT_H,
    }

    try:
        qr = qrcode.QRCode(
            error_correction=levels.get(error_correction, qrcode.constants.ERROR_CORRECT_M),
            box_size=1, border=border,
        )
        qr.add_data(str(data))
        qr.make(fit=True)
        matrix = qr.get_matrix()  # already includes the quiet zone
    except Exception as e:
        logger.error(f"Error generating QR SVG: {str(e)}")
        return ''

    size = len(matrix)
    rects = []
    for y, row in enumerate(matrix):
        run_start = None
        for x, module in enumerate(row):
            if module and run_start is None:
                run_start = x
            elif not module and run_start is not None:
                rects.append(f'<rect x="{run_start}" y="{y}" width="{x - run_start}" height="1"/>')
                run_start = None
        if run_start is not None:
            rects.append(f'<rect x="{run_start}" y="{y}" width="{size - run_start}" height="1"/>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'shape-rendering="crispEdges" '
        f'role="img" aria-label="{escape(str(data), quote=True)}">'
        f'<rect x="0" y="0" width="{size}" height="{size}" fill="#fff"/>'
        f'<g fill="#000">{"".join(rects)}</g>'
        f'</svg>'
    )


def generate_qr_image(data, box_size=8, border=2):
    """QR code as a PNG buffer — the raster twin of generate_qr_svg, for the
    stored label image where there is no printer to rasterise vectors."""
    import qrcode

    try:
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size, border=border,
        )
        qr.add_data(str(data))
        qr.make(fit=True)
        buffer = BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(buffer, format='PNG')
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"Error generating QR image: {str(e)}")
        return None


def generate_label_image(shipping_label):
    """
    Generate a shipping label image with all delivery information.
    Returns a BytesIO buffer containing the PNG image.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.error("PIL/Pillow not installed. Cannot generate label image.")
        return None

    try:
        # Label dimensions (4x6 inches at 203 DPI - standard shipping label)
        width = 812  # 4 inches
        height = 1218  # 6 inches

        # Create white background
        img = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)

        # Try to use a default font, fall back to default if not available
        try:
            font_large = ImageFont.truetype("arial.ttf", 36)
            font_medium = ImageFont.truetype("arial.ttf", 24)
            font_small = ImageFont.truetype("arial.ttf", 18)
            font_bold = ImageFont.truetype("arialbd.ttf", 28)
        except (OSError, IOError):
            font_large = ImageFont.load_default()
            font_medium = font_large
            font_small = font_large
            font_bold = font_large

        y_position = 20
        padding = 20

        # Header - Company Logo placeholder and label number
        draw.rectangle([10, 10, width - 10, 80], outline='black', width=2)
        draw.text((padding, 25), "EZZY DELIVERY", font=font_large, fill='black')
        draw.text((width - 250, 35), f"#{shipping_label.label_number[-12:]}", font=font_small, fill='black')

        y_position = 100

        # FROM Section
        draw.rectangle([10, y_position, width - 10, y_position + 150], outline='black', width=1)
        draw.text((padding, y_position + 5), "FROM:", font=font_bold, fill='black')
        draw.text((padding, y_position + 35), shipping_label.sender_name[:40], font=font_medium, fill='black')
        draw.text((padding, y_position + 65), shipping_label.sender_address[:50], font=font_small, fill='black')
        draw.text((padding, y_position + 90), f"Tel: {shipping_label.sender_phone}", font=font_small, fill='black')

        y_position += 170

        # TO Section (larger, more prominent)
        draw.rectangle([10, y_position, width - 10, y_position + 200], outline='black', width=3)
        draw.text((padding, y_position + 5), "TO:", font=font_bold, fill='black')
        draw.text((padding, y_position + 40), shipping_label.recipient_name[:40], font=font_large, fill='black')

        # Address with zone/street/building
        address_line = shipping_label.recipient_address[:50] if shipping_label.recipient_address else ""
        draw.text((padding, y_position + 85), address_line, font=font_medium, fill='black')

        zone_info = f"Zone: {shipping_label.recipient_zone or 'N/A'} | Street: {shipping_label.recipient_street or 'N/A'} | Bldg: {shipping_label.recipient_building or 'N/A'}"
        draw.text((padding, y_position + 120), zone_info, font=font_small, fill='black')
        draw.text((padding, y_position + 150), f"Tel: {shipping_label.recipient_phone}", font=font_medium, fill='black')

        y_position += 220

        # Order Information Section
        draw.rectangle([10, y_position, width - 10, y_position + 100], outline='black', width=1)
        draw.text((padding, y_position + 10), f"Order #: {shipping_label.order.order_number}", font=font_bold, fill='black')
        draw.text((padding, y_position + 45), f"Task #: {shipping_label.delivery_task.dl_task_number}", font=font_medium, fill='black')
        draw.text((padding, y_position + 70), f"Date: {timezone.now().strftime('%Y-%m-%d')}", font=font_small, fill='black')

        y_position += 120

        # COD Section (highlighted if COD exists)
        cod_amount = float(shipping_label.cod_amount) if shipping_label.cod_amount else 0
        if cod_amount > 0:
            draw.rectangle([10, y_position, width - 10, y_position + 70], fill='lightgray', outline='black', width=2)
            draw.text((padding, y_position + 10), "CASH ON DELIVERY (COD)", font=font_bold, fill='red')
            draw.text((padding, y_position + 40), f"Amount: QAR {cod_amount:.2f}", font=font_large, fill='red')
        else:
            draw.rectangle([10, y_position, width - 10, y_position + 50], outline='black', width=1)
            draw.text((padding, y_position + 15), "PREPAID - NO COD", font=font_medium, fill='black')

        y_position += 90 if cod_amount > 0 else 70

        # Notes Section
        if shipping_label.delivery_notes:
            draw.rectangle([10, y_position, width - 10, y_position + 60], outline='black', width=1)
            draw.text((padding, y_position + 5), "Notes:", font=font_small, fill='black')
            notes_text = shipping_label.delivery_notes[:100]
            draw.text((padding, y_position + 25), notes_text, font=font_small, fill='black')
            y_position += 70

        # Scannable code — a QR, because drivers scan with a phone camera and a
        # stretched Code128 was coming out too fine to resolve.
        code_data = shipping_label.barcode_data or shipping_label.label_number
        qr_buffer = generate_qr_image(code_data)
        if qr_buffer:
            try:
                qr_img = Image.open(qr_buffer)
                qr_size = 300
                qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)  # keep module edges hard
                qr_y = height - qr_size - 60
                img.paste(qr_img, ((width - qr_size) // 2, qr_y))
                draw.text((padding, height - 45), str(code_data), font=font_medium, fill='black')
            except Exception as e:
                logger.warning(f"Could not add QR code to label: {str(e)}")

        # Save to buffer
        output_buffer = BytesIO()
        img.save(output_buffer, format='PNG', quality=95)
        output_buffer.seek(0)

        return output_buffer

    except Exception as e:
        logger.error(f"Error generating label image: {str(e)}", exc_info=True)
        return None


def create_shipping_label(order, delivery_task):
    """
    Create a shipping label when an order is published to a delivery task.

    Args:
        order: The Order instance
        delivery_task: The DeliveryTask instance

    Returns:
        ShippingLabel instance if successful, None otherwise
    """
    from delivery.models import ShippingLabel

    try:
        # Check if label already exists for this order and task
        existing_label = ShippingLabel.objects.filter(
            order=order,
            delivery_task=delivery_task
        ).first()

        if existing_label:
            logger.info(f"Label already exists for order {order.order_number}")
            return existing_label

        # Get sender info from pickup location
        pickup = order.pickup_location
        sender_name = pickup.pickup_location_title if pickup else order.business.business_name
        sender_address = pickup.locality if pickup else ""
        sender_phone = order.business.business_phone if order.business else ""

        # Generate label number
        label_number = generate_label_number(order, delivery_task)

        # Create the shipping label record
        shipping_label = ShippingLabel.objects.create(
            order=order,
            delivery_task=delivery_task,
            label_number=label_number,
            barcode_data=order.order_number,

            # Sender info
            sender_name=sender_name[:255] if sender_name else "N/A",
            sender_address=sender_address or "N/A",
            sender_phone=sender_phone[:20] if sender_phone else "N/A",

            # Recipient info
            recipient_name=order.customer_name[:255] if order.customer_name else "N/A",
            recipient_address=order.customer_address or "N/A",
            recipient_phone=order.customer_phone[:20] if order.customer_phone else "N/A",
            recipient_zone=order.dl_zone,
            recipient_street=order.dl_street,
            recipient_building=order.dl_building,

            # Delivery details
            cod_amount=order.cod_amount or 0,
            delivery_notes=order.order_notes,

            status='generated'
        )

        # Generate and save label image
        label_buffer = generate_label_image(shipping_label)
        if label_buffer:
            filename = f"{label_number}.png"
            shipping_label.label_file.save(filename, File(label_buffer), save=True)
            logger.info(f"Label image generated and saved for order {order.order_number}")
        else:
            logger.warning(f"Could not generate label image for order {order.order_number}")

        logger.info(f"Shipping label {label_number} created for order {order.order_number}")
        return shipping_label

    except Exception as e:
        logger.error(f"Error creating shipping label for order {order.id}: {str(e)}", exc_info=True)
        return None


def regenerate_label(shipping_label):
    """
    Regenerate a shipping label image (useful after updates).

    Args:
        shipping_label: The ShippingLabel instance to regenerate

    Returns:
        True if successful, False otherwise
    """
    try:
        label_buffer = generate_label_image(shipping_label)
        if label_buffer:
            filename = f"{shipping_label.label_number}.png"
            # Delete old file if exists
            if shipping_label.label_file:
                shipping_label.label_file.delete(save=False)
            shipping_label.label_file.save(filename, File(label_buffer), save=True)
            logger.info(f"Label {shipping_label.label_number} regenerated successfully")
            return True
        return False
    except Exception as e:
        logger.error(f"Error regenerating label {shipping_label.label_number}: {str(e)}", exc_info=True)
        return False


def void_label(shipping_label, reason=None):
    """
    Void a shipping label.

    Args:
        shipping_label: The ShippingLabel instance to void
        reason: Optional reason for voiding

    Returns:
        True if successful, False otherwise
    """
    try:
        shipping_label.status = 'void'
        if reason:
            shipping_label.delivery_notes = f"VOIDED: {reason}\n{shipping_label.delivery_notes or ''}"
        shipping_label.save()
        logger.info(f"Label {shipping_label.label_number} voided")
        return True
    except Exception as e:
        logger.error(f"Error voiding label {shipping_label.label_number}: {str(e)}", exc_info=True)
        return False
