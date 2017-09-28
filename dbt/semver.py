import re

from dbt.exceptions import VersionsNotCompatibleException
import dbt.utils

_MATCHERS = "(?P<matcher>\>=|\>|\<|\<=|=)?"
_NUM_NO_LEADING_ZEROS = "(0|[1-9][0-9]*)"
_ALPHA = "[0-9A-Za-z-]*"
_ALPHA_NO_LEADING_ZEROS = "(0|[1-9A-Za-z-][0-9A-Za-z-]*)"

_BASE_VERSION_REGEX = """
(?P<major>{num_no_leading_zeros})\.
(?P<minor>{num_no_leading_zeros})\.
(?P<patch>{num_no_leading_zeros})
""".format(num_no_leading_zeros=_NUM_NO_LEADING_ZEROS)

_VERSION_EXTRA_REGEX = """
(\-
  (?P<prerelease>
    {alpha_no_leading_zeros}(\.{alpha_no_leading_zeros})*))?
(\+
  (?P<build>
    {alpha}(\.{alpha})*))?
""".format(
    alpha_no_leading_zeros=_ALPHA_NO_LEADING_ZEROS,
    alpha=_ALPHA)

_VERSION_REGEX = re.compile("""
^
{matchers}
{base_version_regex}
{version_extra_regex}
$
""".format(
    matchers=_MATCHERS,
    base_version_regex=_BASE_VERSION_REGEX,
    version_extra_regex=_VERSION_EXTRA_REGEX),
                            re.VERBOSE)


class Matchers:
    GREATER_THAN = '>'
    GREATER_THAN_OR_EQUAL = '>='
    LESS_THAN = '<'
    LESS_THAN_OR_EQUAL = '<='
    EXACT = '='


class VersionRange(dbt.utils.AttrDict):

    def _try_combine_exact(self, a, b):
        if a.compare(b) == 0:
            return a
        else:
            raise VersionsNotCompatibleException()

    def _try_combine_lower_bound_with_exact(self, lower, exact):
        comparison = lower.compare(exact)

        if(comparison < 0 or
           (comparison == 0 and
            lower.matcher == Matchers.GREATER_THAN_OR_EQUAL)):
            return exact

        raise VersionsNotCompatibleException()

    def _try_combine_lower_bound(self, a, b):
        if b.is_unbounded:
            return a
        elif a.is_unbounded:
            return b

        if not (a.is_exact or b.is_exact):
            comparison = (a.compare(b) < 0)

            if comparison:
                return b
            else:
                return a

        elif a.is_exact:
            return self._try_combine_lower_bound_with_exact(b, a)

        elif b.is_exact:
            return self._try_combine_lower_bound_with_exact(a, b)

    def _try_combine_upper_bound_with_exact(self, upper, exact):
        comparison = upper.compare(exact)

        if(comparison > 0 or
           (comparison == 0 and
            upper.matcher == Matchers.LESS_THAN_OR_EQUAL)):
            return exact

        raise VersionsNotCompatibleException()

    def _try_combine_upper_bound(self, a, b):
        if b.is_unbounded:
            return a
        elif a.is_unbounded:
            return b

        if not (a.is_exact or b.is_exact):
            comparison = (a.compare(b) > 0)

            if comparison:
                return b
            else:
                return a

        elif a.is_exact:
            return self._try_combine_upper_bound_with_exact(b, a)

        elif b.is_exact:
            return self._try_combine_upper_bound_with_exact(a, b)

    def reduce(self, other):
        start = None

        if(self.start.is_exact and other.start.is_exact):
            start = end = self._try_combine_exact(self.start, other.start)

        else:
            start = self._try_combine_lower_bound(self.start, other.start)
            end = self._try_combine_upper_bound(self.end, other.end)

        if start.compare(end) > 0:
            raise VersionsNotCompatibleException()

        return VersionRange(start=start, end=end)


class VersionSpecifier(dbt.utils.AttrDict):

    def __init__(self, *args, **kwargs):
        super(VersionSpecifier, self).__init__(*args, **kwargs)

        if self.matcher is None:
            self.matcher = Matchers.EXACT

    @classmethod
    def from_version_string(cls, version_string):
        match = _VERSION_REGEX.match(version_string)

        if match is None:
            # error?
            return None

        return VersionSpecifier(match.groupdict())

    def to_range(self):
        range_start = UnboundedVersionSpecifier()
        range_end = UnboundedVersionSpecifier()

        if self.matcher == Matchers.EXACT:
            range_start = self
            range_end = self

        elif self.matcher in [Matchers.GREATER_THAN,
                              Matchers.GREATER_THAN_OR_EQUAL]:
            range_start = self

        elif self.matcher in [Matchers.LESS_THAN,
                              Matchers.LESS_THAN_OR_EQUAL]:
            range_end = self

        return VersionRange(
            start=range_start,
            end=range_end)

    def compare(self, other):
        if self.is_unbounded or other.is_unbounded:
            return 0

        for key in ['major', 'minor', 'patch']:
            comparison = int(self[key]) - int(other[key])

            if comparison != 0:
                return comparison

        if((self.matcher == Matchers.GREATER_THAN_OR_EQUAL and
            other.matcher == Matchers.LESS_THAN_OR_EQUAL) or
           (self.matcher == Matchers.LESS_THAN_OR_EQUAL and
            other.matcher == Matchers.GREATER_THAN_OR_EQUAL)):
            return 0

        if((self.matcher == Matchers.LESS_THAN and
            other.matcher == Matchers.LESS_THAN_OR_EQUAL) or
           (other.matcher == Matchers.GREATER_THAN and
            self.matcher == Matchers.GREATER_THAN_OR_EQUAL) or
           (self.is_upper_bound and other.is_lower_bound)):
            return -1

        if((other.matcher == Matchers.LESS_THAN and
            self.matcher == Matchers.LESS_THAN_OR_EQUAL) or
           (self.matcher == Matchers.GREATER_THAN and
            other.matcher == Matchers.GREATER_THAN_OR_EQUAL) or
           (self.is_lower_bound and other.is_upper_bound)):
            return 1

        return 0

    @property
    def is_unbounded(self):
        return False

    @property
    def is_lower_bound(self):
        return self.matcher in [Matchers.GREATER_THAN,
                                Matchers.GREATER_THAN_OR_EQUAL]

    @property
    def is_upper_bound(self):
        return self.matcher in [Matchers.LESS_THAN,
                                Matchers.LESS_THAN_OR_EQUAL]

    @property
    def is_exact(self):
        return self.matcher == Matchers.EXACT


class UnboundedVersionSpecifier(VersionSpecifier):

    def __init__(self, *args, **kwargs):
        super(dbt.utils.AttrDict, self).__init__(*args, **kwargs)

    @property
    def is_unbounded(self):
        return True

    @property
    def is_lower_bound(self):
        return False

    @property
    def is_upper_bound(self):
        return False

    @property
    def is_exact(self):
        return False


def reduce_versions(*args):
    version_specifiers = [
        VersionSpecifier.from_version_string(version_string)
        for version_string in args]

    for version_specifier in version_specifiers:
        if not isinstance(version_specifier, VersionSpecifier):
            raise Exception(version_specifier)

    try:
        to_return = version_specifiers.pop().to_range()

        for version_specifier in version_specifiers:
            to_return = to_return.reduce(version_specifier.to_range())
    except VersionsNotCompatibleException as e:
        raise VersionsNotCompatibleException(
            'Could not find a satisfactory version from options: {}'
            .format(str(args)))

    return to_return

def versions_compatible(*args):
    if len(args) == 1:
        return True

    try:
        reduce_versions(*args)
        return True
    except VersionsNotCompatibleException as e:
        return False
