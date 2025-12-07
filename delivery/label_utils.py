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
    """Generate a unique label number based on order and task info"""
    timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
    short_uuid = str(uuid.uuid4()).replace('-', '').upper()[:6]
    return f"LBL-{order.business.business_code}-{order.order_number}-{short_uuid}"


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

        # Barcode Section
        barcode_buffer = generate_barcode_image(shipping_label.barcode_data or shipping_label.label_number)
        if barcode_buffer:
            try:
                barcode_img = Image.open(barcode_buffer)
                # Resize barcode to fit
                barcode_width = width - 40
                barcode_height = int(barcode_img.height * (barcode_width / barcode_img.width))
                barcode_img = barcode_img.resize((barcode_width, barcode_height))

                # Calculate position to paste barcode
                barcode_y = height - barcode_height - 30
                img.paste(barcode_img, (20, barcode_y))
            except Exception as e:
                logger.warning(f"Could not add barcode to label: {str(e)}")

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
