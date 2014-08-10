from google.appengine.ext import ndb
from google.appengine.api import users

import os
import json
import jinja2
import logging
import webapp2
import urllib2
import datetime
import time

class Student(ndb.Model):
	name = ndb.StringProperty(required=True)
	uni = ndb.StringProperty()
	birthday = ndb.DateProperty()

	def url(self):
		return "/profile?ID=%s" % self.key.id()

	# Bulk Deletions Later
	def delete(self):
		self.key.delete()

jinja_environment = jinja2.Environment(loader=
	jinja2.FileSystemLoader(os.path.dirname(__file__)))

# Bootstrap and Parsely
header = "<head><link rel=\"stylesheet\" type=\"text/css\" href=\"http://maxcdn.bootstrapcdn.com/bootstrap/3.2.0/css/bootstrap.min.css\">	<script src=\"http://code.jquery.com/jquery-git1.min.js\"></script>	<script src=\"http://maxcdn.bootstrapcdn.com/bootstrap/3.2.0/js/bootstrap.min.js\"></script>	<link rel=\"stylesheet\" type=\"text/css\" href=\"http://parsleyjs.org/src/parsley.css\">	<script src=\"https://cdnjs.cloudflare.com/ajax/libs/parsley.js/2.0.2/parsley.min.js\"></script>	</head>"

def SetTemplate(pageName):
	return jinja_environment.get_template("%s.html" % pageName)

class DashboardHandler(webapp2.RequestHandler):
	def get(self):
		self.response.out.write(header)

		pageName = "dashboard"
		template = SetTemplate(pageName)

		results = Student.query().fetch()
		template_values = { "students" : results }

		self.response.out.write(template.render(template_values))

class ProfileHandler(webapp2.RequestHandler):
	def get(self):
		self.response.out.write(header)

		pageName = "student"
		template = SetTemplate(pageName)

		if self.request.get("new") == "true":
			name = str(self.request.get("name"))
			uni = self.request.get("uni")
			birthday = str(self.request.get("birthday"))
			
			if birthday == "":
				birthday = datetime.datetime.strptime("1900-1-1", "%Y-%m-%d")
			else:
				birthday = datetime.datetime.strptime(birthday, "%Y-%m-%d")

			student = Student(name=name, uni=uni, birthday=birthday)
			student.put()
		else:
			ID = int(self.request.get("ID"))
			student = Student.get_by_id(ID)
			name = student.name
			uni = student.uni
			birthday = student.birthday

		template_values = {
			"student" :
				{
					"name" : name,
					"uni" : uni,
					"birthday" : birthday,
				}
		}

		# template_values["photos"] = GetPictures(template_values["student"]["uni"])
		self.response.out.write(template.render(template_values))

# Start Generic Handlers

class GenericHandler(webapp2.RequestHandler):
	def __init__(self, request, response):
		self.initialize(request, response)
		self.get()
		self.response.out.write(header)
		template = SetTemplate(self.pageName)
		self.response.out.write(template.render())

class SingupHandler(GenericHandler):
	def get(self):
		self.pageName = "signup"

class NotFoundHandler(GenericHandler):
	def get(self):
		self.pageName = "404"

# End Generic Handlers

# For deletion => self.redirect

def GetAnswers(inputValues):
	answers = []
	guesses = inputValues.keys()
	correct = [ "7", "Sacramento"]
	questions = [ "What is 3 + 4?", "What is the capital of California?" ]

	for index in xrange(0, len(inputValues)):
		answers.append({
		"guess" : guesses[index],
		"correct" : correct[index],
		"questions" : questions[index],
		})

	return answers

routes = [
		("/profile", ProfileHandler),
		("/dashboard", DashboardHandler),
		("/signup", SingupHandler),
		("/", SingupHandler),
		("/.*", NotFoundHandler),
]

app = webapp2.WSGIApplication(routes, debug=True)