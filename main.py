from webapp2_extras.auth import InvalidPasswordError
from webapp2_extras.auth import InvalidAuthIdError

from google.appengine.ext import ndb

from webapp2_extras import sessions
from webapp2_extras import auth

from models import User, Lab

import urllib, hashlib
import webapp2
import logging
import jinja2
import time
import os

jinja_environment = jinja2.Environment(loader=
		jinja2.FileSystemLoader(os.path.dirname(__file__)))

# Start Authentication

def user_required(handler):
	"""
		Decorator that checks if there's a user associated with the current session.
		Will also fail if there's no session present.
	"""
	def check_login(self, *args, **kwargs):
		auth = self.auth
		if not auth.get_user_by_session():
			self.redirect(self.uri_for('login'))
		else:
			return handler(self, *args, **kwargs)

	return check_login

class BaseHandler(webapp2.RequestHandler):
	@webapp2.cached_property
	def auth(self):
		"""Shortcut to access the auth instance as a property."""
		return auth.get_auth()

	@webapp2.cached_property
	def user_info(self):
		"""Shortcut to access a subset of the user attributes that are stored
		in the session.

		The list of attributes to store in the session is specified in
			config['webapp2_extras.auth']['user_attributes'].
		:returns
			A dictionary with most user information
		"""
		return self.auth.get_user_by_session()

	@webapp2.cached_property
	def user(self):
		"""Shortcut to access the current logged in user.

		Unlike user_info, it fetches information from the persistence layer and
		returns an instance of the underlying model.

		:returns
			The instance of the user model associated to the logged in user.
		"""
		u = self.user_info
		return self.user_model.get_by_id(u['user_id']) if u else None

	@webapp2.cached_property
	def user_model(self):
		"""Returns the implementation of the user model.

		It is consistent with config['webapp2_extras.auth']['user_model'], if set.
		"""	 
		return self.auth.store.user_model

	@webapp2.cached_property
	def session(self):
			"""Shortcut to access the current session."""
			return self.session_store.get_session(backend="datastore")

	def render_template(self, view_filename, params=None):
		if not params:
			params = {}
		user = self.user
		params['user'] = user
		template = jinja_environment.get_template('views/%s.html' % view_filename)
		self.response.out.write(template.render(params))

	def display_message(self, message):
		"""Utility function to display a template with a simple message."""
		params = {
			'message': message
		}
		self.render_template('message', params)

	# this is needed for webapp2 sessions to work
	def dispatch(self):
			# Get a session store for this request.
			self.session_store = sessions.get_store(request=self.request)

			try:
				# Dispatch the request.
				webapp2.RequestHandler.dispatch(self)
			finally:
				# Save all sessions.
				self.session_store.save_sessions(self.response)

	def abort(self):
		NotFoundHandler(self)

class NotFoundHandler(BaseHandler):
	def get(self):
		self.render_template('404')

class MainHandler(BaseHandler):
	def get(self):
		if self.user:
			self.redirect(self.user.profile_link())
		else:
			params = { "splash" : True }
			self.render_template('login', params)

class SignupHandler(BaseHandler):
	def get(self):
		self.render_template('login')

	def post(self):
		email = self.request.get('email')
		name = self.request.get('name')
		password = self.request.get('password')
		last_name = self.request.get('lastname')

		unique_properties = ['email_address']
		user_data = self.user_model.create_user(email,
			unique_properties, email_address=email, name=name, password_raw=password,
			last_name=last_name, verified=False)
		if not user_data[0]: #user_data is a tuple
			self.display_message('Unable to create user for email %s because of \
				duplicate keys %s' % (email_address, user_data[1]))
			return
		
		user = user_data[1]
		user_id = user.get_id()

		token = self.user_model.create_signup_token(user_id)

		verification_url = self.uri_for('verification', type='v', user_id=user_id,
			signup_token=token, _full=True)

		msg = 'Send an email to user in order to verify their address. \
					They will be able to do so by visiting <a href="{url}">{url}</a>'

		self.display_message(msg.format(url=verification_url))

class ForgotPasswordHandler(BaseHandler):
	def get(self):
		self._serve_page()

	def post(self):
		email = self.request.get('email')

		user = self.user_model.get_by_auth_id(email)
		if not user:
			logging.info('Could not find any user entry for email %s', email)
			self._serve_page(not_found=True)
			return

		user_id = user.get_id()
		token = self.user_model.create_signup_token(user_id)

		verification_url = self.uri_for('verification', type='p', user_id=user_id,
			signup_token=token, _full=True)

		msg = 'Send an email to user in order to reset their password. \
					They will be able to do so by visiting <a href="{url}">{url}</a>'

		self.display_message(msg.format(url=verification_url))
	
	def _serve_page(self, not_found=False):
		email = self.request.get('email')
		params = {
			'email': email,
			'not_found': not_found
		}
		self.render_template('forgot', params)

class VerificationHandler(BaseHandler):
	def get(self, *args, **kwargs):
		user = None
		user_id = kwargs['user_id']
		signup_token = kwargs['signup_token']
		verification_type = kwargs['type']

		# it should be something more concise like
		# self.auth.get_user_by_token(user_id, signup_token)
		# unfortunately the auth interface does not (yet) allow to manipulate
		# signup tokens concisely
		user, ts = self.user_model.get_by_auth_token(int(user_id), signup_token,
			'signup')

		if not user:
			logging.info('Could not find any user with id "%s" signup token "%s"',
				user_id, signup_token)
			self.abort()

		# store user data in the session
		self.auth.set_session(self.auth.store.user_to_dict(user), remember=True)

		if verification_type == 'v':
			# remove signup token, we don't want users to come back with an old link
			self.user_model.delete_signup_token(user.get_id(), signup_token)

			if not user.verified:
				user.verified = True
				user.put()

			self.display_message('User email address has been verified.')
			return
		elif verification_type == 'p':
			# supply user to the page
			params = {
				'user': user,
				'token': signup_token
			}
			self.render_template('resetpassword', params)
		else:
			logging.info('verification type not supported')
			self.abort()

class SetPasswordHandler(BaseHandler):
	@user_required
	def post(self):
		password = self.request.get('password')
		old_token = self.request.get('t')

		if not password or password != self.request.get('confirm_password'):
			self.display_message('passwords do not match')
			return

		user = self.user
		user.set_password(password)
		user.put()

		# remove signup token, we don't want users to come back with an old link
		self.user_model.delete_signup_token(user.get_id(), old_token)
		
		self.display_message('Password updated')

class LoginHandler(BaseHandler):
	def get(self):
		if self.user:
			self.redirect(self.user.profile_link())
		else:
			self._serve_page()

	def post(self):
		email = self.request.get('email')
		password = self.request.get('password')
		try:
			u = self.auth.get_user_by_password(email, password, remember=True,
				save_session=True)
			self.redirect(self.uri_for('home'))
		except (InvalidAuthIdError, InvalidPasswordError) as e:
			logging.info('Login failed for user %s because of %s', email, type(e))
			self._serve_page(True)

	def _serve_page(self, failed=False):
		email = self.request.get('email')
		params = {
			'email': email,
			'failed': failed
		}
		self.render_template('login', params)

class LogoutHandler(BaseHandler):
	def get(self):
		self.auth.unset_session()
		self.redirect(self.uri_for('home'))

config = {
	'webapp2_extras.auth': {
		'user_model': 'models.User',
		'user_attributes': ['name']
	},
	'webapp2_extras.sessions': {
		'secret_key': '{z-0NJ]?VmFZTWvHX{;jGzO<c4-@Uk58 b|Ak }_wu+1mWk )>Vc5K7{b--fj%%l'
	}
}

# End Authentication?

class ProfileHandler(BaseHandler):
	@user_required
	def get(self, *args, **kwargs):
		user_id = int(kwargs['user_id'])
		name = kwargs['name'].lower()
		request_type = kwargs['type'].lower()
		last_name = kwargs['last_name'].lower()

		local_user = User.get_by_id(user_id)
		user = self.user
		if request_type == 'p':
			if local_user and local_user.name.lower() == name and local_user.key.id() == user_id:
				query = Lab.query()
				if local_user.key.id() == user.key.id():
					labs = query.filter(Lab.collaborators.IN([local_user.email_address])).fetch()
				else:
					labs = query.filter(Lab.collaborators.IN([local_user.email_address]) and Lab.private == False).fetch()
				params = {
				'labs': labs,
				'local_user': local_user
				}
				self.render_template('profile', params)
			else:
				self.display_message('The user who\'s profile you attempted to view does not exist. <a href="/p/{0}.{1}/{2}">Go your profile.</a>'.format(user.name, user.last_name, user.key.id()))
		else:
			self.redirect(self.uri_for('home'))

# Lab Handlers

class NewLabHandler(BaseHandler):
	@user_required
	def get(self):
		self.render_template('new_lab')

	def post(self):
		name = self.request.get('name')
		owner = self.request.get('owner')
		collaborators = self.request.get('emails') + ',' + owner
		private = self.request.get('private')
		if private.lower() == 'true':
			private = True
		else:
			private = False
		
		lab = Lab(name = name,
				owner = owner,
				private = private,
				collaborators = collaborators.split(","))
		lab.put()

		time.sleep(0.1)
		self.redirect(self.uri_for('home'))

class LabHandler(BaseHandler):
	@user_required
	def get(self, *args, **kwargs):
		lab_id = kwargs['lab_id']
		lab = Lab.get_by_id(int(lab_id))
		if lab:
			params = {
				'lab': lab
			}
			lab.put()
			self.render_template('lab', params)
		else:
			params = {
				'lab_id': lab_id
			}
			self.display_message('There is no such lab registered under your name. <a href="/new_lab">Create A New Lab</a>')

class DeleteLabHandler(webapp2.RequestHandler):
	def post(self):
		lab_id = int(self.request.get('id'))
		lab = Lab.get_by_id(lab_id)
		if lab:
			lab.key.delete()
			time.sleep(0.1)
			self.redirect(self.uri_for('home'))
		else:
			self.display_message('There is no lab by this id.')

# End labs

routes = [
		webapp2.Route('/', MainHandler, name='home'),
		webapp2.Route('/signup', SignupHandler),
		webapp2.Route('/<type:v|p>/<user_id:\d+>-<signup_token:.+>',
			handler=VerificationHandler, name='verification'),
		webapp2.Route('/<type:l|p>/<lab_id:\d+>',
			handler=LabHandler, name='lab'),
		webapp2.Route('/new_lab',
			handler=NewLabHandler, name='newlab'),
		webapp2.Route('/<type:u|p>/<name:.+>.<last_name:.+>/<user_id:\d+>',
			handler=ProfileHandler, name='profile'),
		webapp2.Route('/delete_lab', DeleteLabHandler),
		webapp2.Route('/password', SetPasswordHandler),
		webapp2.Route('/login', LoginHandler, name='login'),
		webapp2.Route('/logout', LogoutHandler, name='logout'),
		webapp2.Route('/forgot', ForgotPasswordHandler, name='forgot'),
		webapp2.Route("/profile", MainHandler),
		("/.*", NotFoundHandler),
]

app = webapp2.WSGIApplication(routes, debug=False, config=config)