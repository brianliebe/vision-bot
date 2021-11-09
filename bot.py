import os
import discord
import requests
import json
import proto

from google.cloud import vision
from gcloud import storage
from random import random
from PIL import Image, ImageDraw, ImageFont

image_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'images')

# Discord setup
d_token = os.getenv('DISCORD_TOKEN')
d = discord.Client()

# Google setup
client = vision.ImageAnnotatorClient()
storage = storage.Client()
bucket = storage.get_bucket('image-bot-bucket')

def upload_image_from_url(image_url):
    """
    upload_image_from_url: Takes a Discord URL and uploads that image to the Google Bucket
    :param image_url: The Discord URL for an image
    :return: The Google Bucket gs:// URL for the image
    """
    image_id = str(int(random() * 10000000)) # generate a random ID for this image (TODO: make unique)
    blob_name = 'discordimages/{}_original.jpg'.format(image_id)
    blob = bucket.blob(blob_name)

    img_data = requests.get(image_url).content
    with open("{}/{}_original.jpg".format(image_dir, image_id), 'wb') as handler:
        handler.write(img_data)
    blob.upload_from_filename("{}/{}_original.jpg".format(image_dir, image_id))
    return "gs://image-bot-bucket/discordimages/{}_original.jpg".format(image_id), image_id

def get_response(analysis):
    """
    get_response: Takes the analysis from Google Vision and returns a human-friendly explanation
    :param analysis: The analysis from Google Vision in json format
    :return: A human-friendly explanation of the analysis
    """
    all_matches = []
    for o in analysis['localizedObjectAnnotations']:
        all_matches.append([o['name'], int(o['score'] * 100)])
    if len(all_matches) == 0:
        return None
    elif len(all_matches) == 1:
        return "Looks like: '{}' (Probability: {}%)".format(all_matches[0][0], all_matches[0][1])
    else:
        msg = "Looks like: '{}' (Probability: {}%)\nOther guesses: ".format(all_matches[0][0], all_matches[0][1])
        for i, match in enumerate(all_matches[1:]):
            msg += "{} ({}%)".format(match[0], match[1])
            if i < len(all_matches) - 2:
                msg += ", "
        return msg

def get_annotated_image(analysis, image_id):
    """
    get_annotated_image: Annotate the image with boxes/text to explain what Vision has discovered
    :param analysis: Analysis from Google Vision as json
    :param image_id: The ID we generated for this image
    :return: An annotated image
    """
    filename = "{}/{}_original.jpg".format(image_dir, image_id)
    image = Image.open(filename)
    draw = ImageDraw.Draw(image)
    width, height = image.size
    font = ImageFont.truetype('/Library/Fonts/Arial.ttf', 90 if width > 1500 else 40)

    for o in analysis['localizedObjectAnnotations']:
        text = "{} ({}%)".format(o['name'], int(o['score'] * 100))
        x0, y0 = o['boundingPoly']['normalizedVertices'][0]['x'], o['boundingPoly']['normalizedVertices'][0]['y']
        x1, y1 = o['boundingPoly']['normalizedVertices'][2]['x'], o['boundingPoly']['normalizedVertices'][2]['y']
        draw.rectangle([(x0 * width, y0 * height), (x1 * width, y1 * height)], width = int(width * 0.003), outline="#FF0000")
        draw.text((x0 * width + 10, y0 * height + 5), text, "#FF0000", font=font)
    try:
        image.save("{}/{}_annotated.jpg".format(image_dir, image_id))
        return "{}/{}_annotated.jpg".format(image_dir, image_id)
    except OSError as e:
        image.save("{}/{}_annotated.png".format(image_dir, image_id))
        return "{}/{}_annotated.png".format(image_dir, image_id)
    except Exception as e:
        print(e)
        return None


@d.event
async def on_message(message):
    if message.author == d.user: return
    if message.attachments:
        uri, image_id = upload_image_from_url(str(message.attachments[0]))
        full_analysis = client.annotate_image({
            'image': {'source': {'image_uri': uri}},
            'features': [{'type_': vision.Feature.Type.OBJECT_LOCALIZATION}]
        })
        analysis = json.loads(proto.Message.to_json(full_analysis))
        response = get_response(analysis)
        response_image = get_annotated_image(analysis, image_id)
        if response is not None:
            if response_image is None:
                await message.channel.send("Sorry, couldn't process that image :/")
            else:
                await message.channel.send(response, file=discord.File(response_image))
        else:
            await message.channel.send("Sorry, doesn't look like anything to me :/")

d.run(d_token)