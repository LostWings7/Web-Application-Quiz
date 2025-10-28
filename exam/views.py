from django.shortcuts import render, redirect, get_object_or_404 
from django.http import HttpResponse 
from django.template import loader 
from django.db.models import Avg, Max, Min, Count, Q
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from collections import defaultdict,Counter
from .models import Quiz, Question, QuizResult, Subtopic
from .forms import CodeForm
from xhtml2pdf import pisa
from io import BytesIO
import random
import csv
import json


def home(request):
    return render(request, 'home.html')

@login_required 
def main(request): 
	username = request.user.username 
	template = loader.get_template('base.html') 
	context = {'username': username} 
	return HttpResponse(template.render(context, request))

def render_results(request):
	results=QuizResult.objects.filter(user=request.user).select_related('quiz')
	template = loader.get_template('quiz_results.html')
	context = {'results':results}
	return HttpResponse(template.render(context, request))

@login_required 
def enter_code_view(request):
	request.session.pop('quiz_answers', None) 
	if request.method=='POST': 
		form = CodeForm(request.POST) 
		if form.is_valid(): 
			code = form.cleaned_data['code'] 
			try: 
				quiz = Quiz.objects.get(code=code) 
				return redirect('quiz_question', quiz_id=quiz.id, question_num=1) 
			except Quiz.DoesNotExist: 
				form.add_error('code', 'Invalid code, Please try again') 
	else: 
		form = CodeForm() 
	return render(request, 'enter_code.html', {'form': form})

@login_required 
def quiz_question_view(request, quiz_id, question_num):
	quiz = get_object_or_404(Quiz, id=quiz_id)

	if QuizResult.objects.filter(quiz=quiz, user=request.user).exists():
	    return render(request, 'quiz_already_done.html')

	question_ids = request.session.get(f'quiz_{quiz_id}_order')
	if not question_ids:
		questions = list(Question.objects.filter(quiz=quiz).values_list('id',flat=True))
		random.shuffle(questions)
		request.session[f'quiz_{quiz_id}_order']=questions
		question_ids = questions

	question_ordered = Question.objects.filter(id__in=question_ids)
	question_map = {q.id: q for q in question_ordered}
	questions = [question_map[qid] for qid in question_ids]

	total_questions = len(questions)

	try:
	    current_question_id = question_ids[int(question_num) - 1]
	    current_question = Question.objects.get(id = current_question_id)
	except (IndexError, Question.DoesNotExist):
	    return redirect('quiz_question', quiz_id=quiz.id, question_num=1)

	quiz_answers = request.session.get('quiz_answers', {})

	if request.method == 'POST':
	    answer = request.POST.get('answer')
	    quiz_answers[str(current_question.id)] = answer
	    request.session['quiz_answers'] = quiz_answers
	    request.session.modified = True

	    if 'prev' in request.POST:
	        prev_q = int(question_num) - 1
	        return redirect('quiz_question', quiz_id=quiz.id, question_num=prev_q)
	    else:
	        next_q = int(question_num) + 1
	        if next_q <= total_questions:
	            return redirect('quiz_question', quiz_id=quiz.id, question_num=next_q)
	        else:
	            return redirect('quiz_submit', quiz_id=quiz.id)

	selected_answer = quiz_answers.get(str(current_question.id), '')

	return render(request, 'quiz_question.html', {
	    'quiz': quiz,
	    'question': current_question,
	    'question_num': int(question_num),
	    'total_questions': total_questions,
	    'questions': questions,
	    'selected_answer': selected_answer,
	    'answered_ids': [qid for qid, ans in quiz_answers.items() if ans]
	})

@login_required 
def quiz_submit_view(request, quiz_id): 
	quiz = get_object_or_404(Quiz, id=quiz_id)

	if QuizResult.objects.filter(quiz=quiz, user=request.user).exists():
	    return render(request, 'quiz_already_done.html')

	questions = Question.objects.filter(quiz=quiz)
	answers = request.session.get('quiz_answers', {})
	total_questions=questions.count()
	score = 0

	for q in questions:
	    if answers.get(str(q.id)) == q.correct_answer:
	        score += 1

	quiz_result = QuizResult.objects.create(
	    quiz=quiz,
	    user=request.user,
	    score=score,
	    answers=answers,
	)

	if 'quiz_answers' in request.session:
	    del request.session['quiz_answers']

	return render(request, 'quiz_completed.html', {'quiz': quiz,})

@staff_member_required
def overall_analysis_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    results = QuizResult.objects.filter(quiz=quiz)
    questions = Question.objects.filter(quiz=quiz)
    total_participants = results.count()
    total_questions=questions.count()

    # Basic stats
    average_score = results.aggregate(avg=Avg('score'))['avg'] or 0
    highest_score = results.aggregate(max=Max('score'))['max'] or 0
    lowest_score = results.aggregate(min=Min('score'))['min'] or 0

    overall_score=0
    length_=0
    bins={
    '0-4':0,
    '4-7':0,
    '7-10':0,
    }
    # Score distribution - rounding to nearest 0.5
    distribution = defaultdict(int)
    for result in results:
    	if 0<=round((result.score/total_questions)*10)<4:
    		bins['0-4']+=1
    	if 4<=round((result.score/total_questions)*10)<7:
    		bins['4-7']+=1
    	if 7<=round((result.score/total_questions)*10)<=10:
    		bins['7-10']+=1
    	overall_score+=round((result.score/total_questions)*100)
    	length_+=1
    	#score to the nearest 0.5
    	rounded_score = round((result.score/total_questions)*20) / 2
    	distribution[rounded_score] += 1

    overall_score/=length_

    # Subtopic-wise accuracy
    subtopic_data = defaultdict(lambda: {'correct': 0, 'total': 0})
    for result in results:
        for q in questions:
            if q.subtopic:
                subtopic_data[q.subtopic.name]['total'] += 1
                if str(q.id) in result.answers and result.answers[str(q.id)] == q.correct_answer:
                    subtopic_data[q.subtopic.name]['correct'] += 1

    subtopic_accuracy = []
    for name, data in subtopic_data.items():
        accuracy = (data['correct'] / data['total']) * 100 if data['total'] else 0
        subtopic_accuracy.append({
            'name': name,
            'accuracy': round(accuracy, 2),
            'total': data['total'],
            'correct': data['correct']
        })

    # Prepare the distribution for the chart
    score_range = [i / 2 for i in range(21)]  # Scores from 0 to 10, in steps of 0.5
    score_data = [distribution.get(score, 0) for score in score_range]

    # Subtopic data
    subtopic_labels = [item['name'] for item in subtopic_accuracy]
    subtopic_values = [item['accuracy'] for item in subtopic_accuracy]

    student_scores = list(results.values('user__username', 'score', 'submitted_at'))
    student_scores.sort(key=lambda x: x['score'], reverse=True)
    for entry in student_scores:
    	entry['score']=round((entry['score']/total_questions)*20)/2
    # Add rank
    for i, s in enumerate(student_scores, start=1):
    	s['rank'] = i

    questions2 = quiz.questions.all().order_by('id')[:5]
    question_labels = ['Q1','Q2','Q3','Q4','Q5']
    question_accuracies = []

    for question in questions2:
        total = results.count()
        correct = 0
        for result in results:
            answer1 = result.answers.get(str(question.id))
            if answer1 == question.correct_answer:
                correct += 1
        accuracy = round((correct / total) * 100) if total else 0
        question_accuracies.append(accuracy)

    cro_counts = defaultdict(int)
    analysis_data = []

    for question in questions:
        total = QuizResult.objects.filter(quiz=quiz).count()
        count_by_option = defaultdict(int)
        correct_answer = question.correct_answer

        for result in QuizResult.objects.filter(quiz=quiz):
            user_answers = result.answers
            answer = user_answers.get(str(question.id))
            count_by_option[answer] += 1

        correct_count = count_by_option.get(correct_answer, 0)
        accuracy = (correct_count / total * 100) if total else 0

        if accuracy < 50:
            cro_counts['critical'] += 1
        elif accuracy < 77:
            cro_counts['recommended'] += 1
        else:
            cro_counts['optional'] += 1

        analysis_data.append({
            'question': question,
            'accuracy': round(accuracy, 1),
        })

    context = {
        'quiz': quiz,
        'total_participants': total_participants,
        'student_scores':student_scores,
        'average_score': round(average_score, 2),
        'highest_score': highest_score,
        'lowest_score': lowest_score,
        'overall_score': round(overall_score, 2),
        'avg_score': round(overall_score/10, 1),
        'distribution': distribution,
        'subtopic_accuracy': subtopic_accuracy,
        'score_bins':bins,
        'score_labels': score_range,
        'score_values': score_data,
        'subtopic_labels': subtopic_labels,
        'subtopic_values': subtopic_values,
        'questions': analysis_data,
        'cro_counts': cro_counts,
        'question_labels': json.dumps(question_labels),
        'question_accuracies': json.dumps(question_accuracies)
    }

    return render(request, 'admin/overall_analysis.html', context)

@staff_member_required
def question_analysis_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    results = QuizResult.objects.filter(quiz=quiz)
    total_attempts = results.count()

    questions_data = []

    for question in quiz.questions.all().order_by('id'):
        option_counts = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
        for result in results:
            answer = result.answers.get(str(question.id), None)
            if answer in option_counts:
                option_counts[answer] += 1
        
        option_percentages = {
            opt: round((count / total_attempts) * 100) if total_attempts else 0
            for opt, count in option_counts.items()
        }

        questions_data.append({
            'text': question.text,
            'options': [
                {'label': 'A', 'text': question.option_a, 'percent': option_percentages['A'], 'is_correct':question.correct_answer=='A'},
                {'label': 'B', 'text': question.option_b, 'percent': option_percentages['B'], 'is_correct':question.correct_answer=='B'},
                {'label': 'C', 'text': question.option_c, 'percent': option_percentages['C'], 'is_correct':question.correct_answer=='C'},
                {'label': 'D', 'text': question.option_d, 'percent': option_percentages['D'], 'is_correct':question.correct_answer=='D'},
            ],
            'correct_answer': question.correct_answer,
        })

    return render(request, 'admin/question_analysis.html', {
        'quiz': quiz,
        'questions': questions_data,
    })

def export_overall_analysis_csv(request, quiz_id):
    quiz = Quiz.objects.get(id=quiz_id)
    results = QuizResult.objects.filter(quiz=quiz).select_related('user')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{quiz.title}_scorecard.csv"'

    writer = csv.writer(response)
    writer.writerow(['Username', 'Score', 'Submitted At'])

    for result in results:
        writer.writerow([result.user.username, result.score])

    return response

def export_overall_analysis_pdf(request, quiz_id):
    quiz = Quiz.objects.get(id=quiz_id)
    results = QuizResult.objects.filter(quiz=quiz).select_related('user')

    html = render_to_string('admin/analysis_pdf_template.html', {
        'quiz': quiz,
        'results': results,
    })

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{quiz.title}_scorecard.pdf"'

    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('PDF generation error', status=500)
    return response

def full_scorecard_view(request, quiz_id):
	quiz=get_object_or_404(Quiz, id=quiz_id)
	results=QuizResult.objects.filter(quiz=quiz).order_by('-score','submitted_at')
	questions = Question.objects.filter(quiz=quiz)

	total_questions=questions.count()

	for idx, r in enumerate(results, start=1):
		r.rank=idx

	for entry in results:
		entry.score=round((entry.score/total_questions)*20)/2

	context={
	'quiz':quiz,
	'results':results,
	}

	return render(request, 'admin/full_scorecard.html', context)

def view_student_response(request, quiz_id, user_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    result = get_object_or_404(QuizResult, quiz=quiz, user_id=user_id)
    answers = result.answers  # stored as {question_id: 'A', ...}

    questions = Question.objects.filter(quiz=quiz).select_related('subtopic')

    response_data = []
    for question in questions:
        selected = answers.get(str(question.id))
        is_correct = selected == question.correct_answer
        response_data.append({
            'question': question.text,
            'options': {
                'A': question.option_a,
                'B': question.option_b,
                'C': question.option_c,
                'D': question.option_d
            },
            'selected': selected,
            'correct': question.correct_answer,
            'is_correct': is_correct
        })

    return render(request, 'admin/student_response.html', {
        'quiz': quiz,
        'user': result.user,
        'response_data': response_data
    })

def cro_chart_view(request, quiz_id):
    quiz = Quiz.objects.get(id=quiz_id)
    questions = Question.objects.filter(quiz=quiz)

    cro_counts = defaultdict(int)
    analysis_data = []

    for question in questions:
        total = QuizResult.objects.filter(quiz=quiz).count()
        count_by_option = defaultdict(int)
        correct_answer = question.correct_answer

        for result in QuizResult.objects.filter(quiz=quiz):
            user_answers = result.answers
            answer = user_answers.get(str(question.id))
            count_by_option[answer] += 1

        correct_count = count_by_option.get(correct_answer, 0)
        accuracy = (correct_count / total * 100) if total else 0

        if accuracy < 50:
            cro_counts['critical'] += 1
        elif accuracy < 77:
            cro_counts['recommended'] += 1
        else:
            cro_counts['optional'] += 1

        analysis_data.append({
            'question': question,
            'accuracy': round(accuracy, 1),
        })

    context = {
        'quiz': quiz,
        'questions': analysis_data,
        'cro_counts': cro_counts,
    }
    return render(request, 'admin/cro_chart.html', context)

def send_quiz_response_email(user, quiz_id, quiz_result):
	if not user.email:
		return

	quiz = get_object_or_404(Quiz, pk=quiz_id)
	result = get_object_or_404(QuizResult, quiz=quiz, user=user)
	answers = result.answers  # stored as {question_id: 'A', ...}

	questions = Question.objects.filter(quiz=quiz).select_related('subtopic')

	response_data = []
	for question in questions:
	    selected = answers.get(str(question.id))
	    is_correct = selected == question.correct_answer
	    response_data.append({
    	    'question': question.text,
	        'options': {
	            'A': question.option_a,
	            'B': question.option_b,
	            'C': question.option_c,
	            'D': question.option_d
	        },
	        'selected': selected,
	        'correct': question.correct_answer,
	        'is_correct': is_correct
	    })
	context = {
	    'quiz': quiz,
	    'user': result.user,
	    'response_data': response_data,
	}

	html_content = render_to_string('emails/quiz_response_email.html', context)

	email = EmailMessage(
    	subject = f"Your Quiz Submission: {quiz_result.quiz.title}",
    	body = html_content,
    	from_email = settings.DEFAULT_FROM_EMAIL,
    	to = [user.email],
		)
	email.content_subtype = 'html'
	email.send()
