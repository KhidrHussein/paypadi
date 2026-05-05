import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

class SixDigitNumericPasswordValidator:
    def validate(self, password, user=None):
        if not re.match(r'^\d{6}$', password):
            raise ValidationError(
                _("The password must be exactly 6 numeric digits."),
                code='password_not_six_digits',
            )

    def get_help_text(self):
        return _("Your password must be exactly 6 numeric digits.")
