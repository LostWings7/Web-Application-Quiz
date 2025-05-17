from django import forms
from .models import Question, Subtopic

class CodeForm(forms.Form):
	code=forms.CharField(label='Enter Quiz Code', max_length=100)

class QuestionAdminForm(forms.ModelForm):
	class Meta:
		model=Question
		fields='__all__'

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		if 'quiz' in self.data:
			try:
				quiz_id=int(self.data.get('quiz'))
				self.fields['subtopic'].queryset=Subtopic.objects.filter(quiz_id=quiz_id)
			except (ValueError, TypeError):
				pass
		elif self.instance.pk:
			self.fields['subtopic'].queryset=Subtopic.objects.filter(quiz=self.instance.quiz)
		else:
			self.fields['subtopic'].queryset=Subtopic.objects.none()