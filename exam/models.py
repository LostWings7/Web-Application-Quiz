from django.db import models
from django.contrib.auth.models import User
from django.db.models import JSONField

# Create your models here.
class Quiz(models.Model):
	code=models.CharField(max_length=100, unique=True)
	title=models.CharField(max_length=200)

	def __str__(self):
		return self.title

class Subtopic(models.Model):
	quiz=models.ForeignKey(Quiz, on_delete=models.CASCADE, null=True, blank=True)
	name=models.CharField(max_length=100)

	def __str__(self):
		return self.name

class Question(models.Model):
	quiz=models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
	text=models.TextField()
	image=models.ImageField(upload_to='questions/',null=True,blank=True)
	subtopic=models.ForeignKey(Subtopic, on_delete=models.CASCADE, null=True, blank=True)
	option_a=models.CharField(max_length=255)
	option_b=models.CharField(max_length=255)
	option_c=models.CharField(max_length=255)
	option_d=models.CharField(max_length=255)
	correct_answer=models.CharField(max_length=1, choices=[('A','A'),('B','B'),('C','C'),('D','D')])

	def __str__(self):
		return self.text

class QuizResult(models.Model):
	quiz=models.ForeignKey(Quiz,on_delete=models.CASCADE)
	user=models.ForeignKey(User,on_delete=models.CASCADE)
	score=models.IntegerField()
	submitted_at=models.DateTimeField(auto_now_add=True)
	answers = JSONField(default=dict) 

class Meta:
	unique_together=('quiz','user')

