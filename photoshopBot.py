import praw
import re
import schedule
import time
from urlparse import urlparse
from threading import Timer
from imgurpython import ImgurClient

## Removed identifying info
REDDIT_CLIENT_ID =''
REDDIT_CLIENT_SECRET =''
REDDIT_USERNAME = ''
REDDIT_PASSWORD = ''
USER_AGENT=''
SUBREDDIT = ''

reddit = praw.Reddit(client_id=REDDIT_CLIENT_ID,
			client_secret=REDDIT_CLIENT_SECRET,
			user_agent=USER_AGENT,
			username = REDDIT_USERNAME,
			password = REDDIT_PASSWORD)

subreddit = reddit.subreddit(SUBREDDIT)

## Removed identifying info
IMGUR_CLIENT_ID = ''
IMGUR_CLIENT_SECRET = ''

imgur = ImgurClient(IMGUR_CLIENT_ID, IMGUR_CLIENT_SECRET)

def get_num_images(submission):
	## Since all top level comments must be an image, we can just check the length of submissions.comments
	up_to_20 = 20 if len(submission.comments) >= 20 else len(submission.comments)
	return up_to_20

def get_images(submission):
	## Dictionary with type {image url: reddit comment}
	reddit_images = {}

	## Only get the top 20 comments. This seemed like a good sample size for a thread but is otherwise arbitrary.
	up_to_20 = get_num_images(submission)

	for top_level_comment in submission.comments[:up_to_20]:
		text = top_level_comment.body
		## Hueristic: By using re.search(), we only find the first image in the comment in order to prevent clutter in the album.
		url_search_string = 'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
		url = re.search(url_search_string, text)
		if url:
			url = url.group(0).rstrip('()*.')
			url_index = text.find(url)
			## url_index is the index of the character at the beginning of our link, ie 'h' in 'https://...'. We go
			## two more indices left, to also splice out the '(' and ']' characters from the [Comment](Link) text structure.
			## Also remove left bracket from [Comment](Link). We now have the comment that was displayed on the original thread.
			text = text[:url_index-2]
			text = text.replace("[","")
			if url == text:
				## Set a placeholder description if the comment is just a plain link without additional text
				reddit_images[url] = "-"
			else:
				reddit_images[url] = text

	return reddit_images

def format_image_link(image_link):
	## If link is of type "imgur.com/a/{id}" or "imgur.com/{id}" , we need to do a bit of formatting
	if 'imgur' in image_link and '.jpg' not in image_link and '.png' not in image_link:
		parsed_link = urlparse(image_link)
		paths = parsed_link.path.split('/')
		if paths[-2] == 'a':
			image_data = imgur.get_album_images(paths[-1])
			## Only need to take the first image from the album as per our heuristic in get_images.
			image_link = image_data[0].link
		else:
			image_link = image_link + '.jpg'

	return image_link

def check_imgur_rate_limit(images):
	## Cost breakdown: For each link in the images dictionary, we format the link (+1 potential call) and then
	## upload the image (+10 calls). We also do this for the original image, so we add +11.
	## The +10 is for our album creation, it might just be +1 but the documentation was not clear.
	cost = len(images) * 11 + 11 + 10
	if cost < imgur.credits['UserRemaining']:
		return True
	else:
		return False

def create_imgur_album(images,submission):
	fields = {'title' : submission.title,
			  'cover' : images.get(submission.url)}
	album = imgur.create_album(fields)
	album_deletehash = album['deletehash']
	album_id = album['id']
	print album_id

	## Make sure first image in the album is the original image
	first_image_link = format_image_link(submission.url)
	imgur.upload_from_url(first_image_link, config = {'description' : '[Original image]', 'album' : album_deletehash}, anon=True)

	## Most of, if not all, of the failed uploads appear to be gifs. I do not know
	## of a way to upload a gif from the API, but this could be a future improvement.
	failed_uploads = []

	all_image_links = images.keys()

	## Exclude last element so we can append a list of failed uploads to it's comment.
	for image_link in all_image_links[:-1]:
		config = {'description' : images.get(image_link),
				  'album' : album_deletehash}
		image_link = format_image_link(image_link)
		try:
			imgur.upload_from_url(image_link, config = config, anon=True)
		except ImgurClientError:
			## Refactor this to failed_uploads[image_link] = images.get(image_link) w/ an improved dictionary and a linked comment included
			failed_uploads.append(image_link)

	image_link = images.keys()[-1]
	image_link = format_image_link(image_link)
	config = {'description' : images.get(image_link),
			  'album' : album_deletehash}

	if len(failed_uploads) > 0:
		failed_uploads= '\n'.join(failed_uploads)
		failed_uploads_header = "\n\n*******\n*******\n\nImage links that were not uploaded:\n\n"
		config['description'] = config['description'] + failed_uploads_header + failed_uploads

	imgur.upload_from_url(image_link, config = config, anon=True)

	return 'https://imgur.com/a/' + album_id

def main():
	## Due to Imgur's rate limiting, only posting on hot submissions seemed to be the most utilitarian appraoch.
	for submission in subreddit.hot():
		## Expand "Replace more" links to get all possible comments
		submission.comments.replace_more(limit=0)
		## Stickied posts are usually from admins, regarding rules or other things that wouldn't make sense to run this bot on.
		if submission.stickied != True:
			images = get_images(submission)
			## Before uploading pics to Imgur, check our rate limit. We could break here, but instead, we keep looping through
			## submissions in case there is a smaller submission with few enough links to not go over out remaining credits.
			if check_imgur_rate_limit(images) and len(images) > 0:
				## Hardcoded response for now, but could randomly select some funnier comments as a future improvement.
				album_url = create_imgur_album(images,submission)
				bot_reply_comment = 'Click on ' + '[this link](' + album_url + ') to see the top ' + str(get_num_images(submission)) + ' images from this thread!'
				submission.reply(bot_reply_comment)

## We only run the script once a day to deal with rate limiting
schedule.every().day.at("00:00").do(main)
while True:
	schedule.run_pending()
	time.sleep(60)
