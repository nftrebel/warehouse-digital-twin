"""
Views аутентификации и управления пользователями.

- Логин / логаут
- Список пользователей (только для администраторов)
- Создание / редактирование / блокировка пользователей
"""

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from .models import User
from .forms import UserCreateForm, UserEditForm


def login_view(request):
    """Страница входа в систему."""
    if request.user.is_authenticated:
        return redirect('ui:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                next_url = request.GET.get('next', 'ui:dashboard')
                return redirect(next_url)
            else:
                return render(request, 'accounts/login.html', {
                    'form': {'errors': True},
                    'error_message': 'Учётная запись заблокирована',
                })
        else:
            return render(request, 'accounts/login.html', {
                'form': {'errors': True},
            })

    return render(request, 'accounts/login.html', {'form': {}})


def logout_view(request):
    """Выход из системы."""
    logout(request)
    return redirect('accounts:login')


def admin_required(view_func):
    """Декоратор: доступ только для администраторов."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not (request.user.role_code == 'admin' or request.user.is_superuser):
            messages.error(request, 'Доступ запрещён. Требуются права администратора.')
            return redirect('ui:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@admin_required
def user_list(request):
    """Список пользователей (UC-11)."""
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'accounts/user_list.html', {
        'active_page': 'users',
        'users': users,
    })


@admin_required
def user_create(request):
    """Создание пользователя."""
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, f'Пользователь "{user.username}" создан')
            return redirect('accounts:user-list')
    else:
        form = UserCreateForm()

    return render(request, 'accounts/user_form.html', {
        'active_page': 'users',
        'form': form,
        'form_title': 'Новый пользователь',
        'is_edit': False,
    })


@admin_required
def user_edit(request, user_id):
    """Редактирование пользователя."""
    user_obj = get_object_or_404(User, pk=user_id)

    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user_obj)
        if form.is_valid():
            user = form.save()
            password = form.cleaned_data.get('password')
            if password:
                user.set_password(password)
                user.save()
            messages.success(request, f'Пользователь "{user.username}" обновлён')
            return redirect('accounts:user-list')
    else:
        form = UserEditForm(instance=user_obj)

    return render(request, 'accounts/user_form.html', {
        'active_page': 'users',
        'form': form,
        'form_title': f'Редактирование: {user_obj.username}',
        'is_edit': True,
    })


@admin_required
def user_toggle_active(request, user_id):
    """Блокировка / разблокировка пользователя."""
    user_obj = get_object_or_404(User, pk=user_id)

    if user_obj.pk == request.user.pk:
        messages.error(request, 'Нельзя заблокировать свою учётную запись')
        return redirect('accounts:user-list')

    user_obj.is_active = not user_obj.is_active
    user_obj.save(update_fields=['is_active'])

    action = 'разблокирован' if user_obj.is_active else 'заблокирован'
    messages.success(request, f'Пользователь "{user_obj.username}" {action}')
    return redirect('accounts:user-list')


@admin_required
def user_delete(request, user_id):
    """Удаление учётной записи пользователя."""
    user_obj = get_object_or_404(User, pk=user_id)

    if user_obj.pk == request.user.pk:
        messages.error(request, 'Нельзя удалить свою учётную запись')
        return redirect('accounts:user-list')

    if request.method == 'POST':
        username = user_obj.username
        user_obj.delete()
        messages.success(request, f'Пользователь "{username}" удалён')
        return redirect('accounts:user-list')

    return render(request, 'accounts/user_confirm_delete.html', {
        'active_page': 'users',
        'user_obj': user_obj,
    })
