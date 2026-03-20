"""
Формы управления пользователями.
"""

from django import forms
from .models import User


class UserCreateForm(forms.ModelForm):
    """Форма создания нового пользователя."""

    password = forms.CharField(
        widget=forms.PasswordInput,
        label='Пароль',
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        label='Подтверждение пароля',
    )

    class Meta:
        model = User
        fields = ['username', 'full_name', 'role_code']

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get('password')
        pw2 = cleaned.get('password_confirm')
        if pw and pw2 and pw != pw2:
            raise forms.ValidationError('Пароли не совпадают')
        return cleaned


class UserEditForm(forms.ModelForm):
    """Форма редактирования существующего пользователя."""

    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        label='Новый пароль',
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        label='Подтверждение пароля',
    )

    class Meta:
        model = User
        fields = ['username', 'full_name', 'role_code']

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get('password')
        pw2 = cleaned.get('password_confirm')
        if pw and pw != pw2:
            raise forms.ValidationError('Пароли не совпадают')
        return cleaned
