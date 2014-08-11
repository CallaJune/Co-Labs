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
header = '<head>	<link rel="stylesheet" type="text/css" href="/s/b/css/bootstrap.css">	<script src="/s/jquery-git1.js"></script>	<script src="/s/b/js/bootstrap.js"></script>	<link rel="stylesheet" type="text/css" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.1.0/css/font-awesome.min.css">	<link rel="stylesheet" type="text/css" href="/s/parsley.css">	<script src="/s/parsley.js"></script>	</head>'

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

		self.response.out.write(template.render(template_values))

# Start Generic Handlers

class GenericHandler(webapp2.RequestHandler):
	def __init__(self, request, response):
		self.initialize(request, response)
		self.get()
		self.response.out.write(header)
		template = SetTemplate(self.pageName)
		self.response.out.write(template.render())

class HomeHandler(GenericHandler):
	def get(self):
		self.pageName = "home"

class SingupHandler(GenericHandler):
	def get(self):
		self.pageName = "signup"

class NotFoundHandler(GenericHandler):
	def get(self):
		self.pageName = "404"

class WorkspaceHandler(GenericHandler):
	def get(self):
		self.pageName = "workspace"

# End Generic Handlers

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
		("/", WorkspaceHandler),
		("/.*", NotFoundHandler),
]

app = webapp2.WSGIApplication(routes, debug=True)