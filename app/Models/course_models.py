# -*- coding: utf-8 -*-
from . import *
import random
from ..main.errors import *
from .user_models import Student
from datetime import datetime

TESTS_PER_PAGE = 6
NOTIFICATIONS_PER_PAGE = 10


class TimeAndRoom(EmbeddedDocument):
    room_name = StringField(required=True)
    room_id = StringField(required=True)
    days = ListField(IntField(), required=True)
    period = IntField(required=True)
    weeks = ListField(IntField(), required=True)

    def to_dict(self):
        return {'room_name': self.room_name, 'room_id': self.room_id, 'days': self.days, 'period':
            self.period, 'weeks': self.weeks}


class SubCourseSetting(EmbeddedDocument):
    allow_late = IntField()


class SubCourse(Document):
    name = StringField(required=True)
    course_id = StringField(primary_key=True)
    sub_id = StringField(required=True)
    teachers = ListField(StringField(), required=True)
    students = ListField(StringField(), required=True)
    times = EmbeddedDocumentListField(TimeAndRoom)

    settings = EmbeddedDocumentField(SubCourseSetting, required=True, default=SubCourseSetting())
    classes = ListField(StringField())
    pending_asks = ListField(ReferenceField('AskForLeave'))

    def to_dict_brief(self):
        return {'course_id': self.course_id, 'course_name': self.name,
                'times': self.get_times_and_rooms_dict()}

    def get_students_dict(self):
        return map(lambda x: x.to_dict_brief_for_teacher(), self.students)

    def get_teachers_dict(self):
        teachers = []
        map(lambda x: teachers.append(x.to_dict_brief()), self.teachers)
        return teachers

    def get_times_and_rooms_dict(self):
        times = []
        map(lambda x: times.append(x.to_dict()), self.times)
        return times

    def get_attendance_list(self, week_no=None, day_no=None, period_no=None, teach_day=None, period=None):
        if teach_day != None and period != None:

            try:
                list_id = self.course_id + '_' + str(teach_day.week) + '_' + str(teach_day.day) + '_' + str(
                    period.num)
                return AttendanceList.objects(
                    list_id=list_id,
                    week_no=teach_day.week,
                    day_no=teach_day.day,
                    period_no=period.num).modify(upsert=True, new=True,
                                                 set_on_insert__list_id=list_id,
                                                 set_on_insert__course_id=self.course_id,
                                                 set_on_insert__week_no=teach_day.week,
                                                 set_on_insert__day_no=teach_day.day,
                                                 set_on_insert__period_no=period.num)
                AttendanceList.objects()
            except DoesNotExist:
                return None
        elif week_no is not None and day_no is not None and period_no is not None:
            try:
                list_id = self.course_id + '_' + str(week_no) + '_' + str(day_no) + '_' + str(period_no)
                return AttendanceList.objects(
                    list_id=list_id, week_no=week_no, day_no=day_no, period_no=period_no).modify(upsert=True, new=True,
                                                                                                 set_on_insert__course_id=self.course_id,
                                                                                                 set_on_insert__week_no=week_no,
                                                                                                 set_on_insert__day_no=day_no,
                                                                                                 set_on_insert__period_no=period_no,
                                                                                                 set_on_insert__absent_students=self.students)
            except DoesNotExist:
                return None

    def is_on(self, week_no, day_no, period_no):
        for time in self.times:
            if week_no in time.weeks and day_no in time.days and period_no == time.period:
                return True
        return False


class AskForLeaveStatus(Enum):
    PENDING = 0
    APPROVED = 1
    DISAPPROVED = 2


class AskForLeave(Document):
    ask_id = ObjectIdField(default=lambda: ObjectId(), primary_key=True)
    student_id = StringField()
    reason = StringField()
    status = IntField(default=0)
    course_id = StringField()
    week_no = IntField()
    day_no = IntField()
    period_no = IntField()
    created_at = DateTimeField(default=lambda: datetime.now())
    viewed_at = DateTimeField()

    def to_dict(self):
        d = {'ask_id': str(self.ask_id), 'student_id': self.student_id, 'status': self.status,
             'course_id': self.course_id, 'week_no': self.week_no, 'day_no': self.day_no,
             'period_no': self.period_no,
             'reason': self.reason, 'created_at': self.created_at.strftime("%Y-%m-%d %H:%M:%S")}
        if self.status != AskForLeaveStatus.PENDING._value_:
            d['viewed_at'] = self.viewed_at.strftime("%Y-%m-%d %H:%M:%S")
        return d

    def get_status(self):
        if self.status is None:
            return None
        return AskForLeave(self.status)

    def is_approved(self):
        return self.status == 1

    def is_pending(self):
        return self.status == 0

    def is_disapproved(self):
        return self.status == 2

    def set_status(self, status):
        self.status = status._value_


class AttendanceStatus(Enum):
    ABSENT = 0
    PRESENT = 1
    HAS_ASKED_FOR_LEAVE = 2


class AttendanceList(Document):
    present_students = ListField(StringField())
    absent_students = ListField(StringField())
    asked_students = ListField(StringField())
    list_id = StringField(primary_key=True)
    course_id = StringField()
    asks = ListField(ReferenceField('AskForLeave'))
    week_no = IntField()
    day_no = IntField()
    period_no = IntField()
    processed = BooleanField(default=False)

    def check_in(self, student_id):
        if student_id in self.asked_students:
            ask = None
            for t_ask in self.asks:
                if t_ask.student_id == student_id:
                    ask = t_ask
            if ask is None:
                self.update(add_to_set__present_students=student_id, pull__asked_students=student_id)
                return
            if ask.is_approved():
                return Error.ASK_FOR_LEAVE_HAS_BEEN_APPROVED
            else:
                self.update(add_to_set__present_students=student_id, pull__asks_for_leave=ask,
                            pull__absent_students=student_id, pull__asked_students=student_id)
        else:
            self.update(add_to_set__present_students=student_id, pull__absent_students=student_id)

    def to_dict(self, course):
        all_students = set(course.students)
        presents = set(self.present_students)
        asked = []
        for ask in self.asks:
            if ask.is_approved():
                asked.append(ask.student_id)
        asked = set(asked)
        return {'absent': list(all_students - presents - asked), 'asked': list(asked),
                'present': self.present_students}

    def get_attendance_status(self, student_id):
        for ask in self.asks:
            if ask.student_id == student_id:
                if ask.is_approved() or ask.is_pending():
                    return ask.to_dict()
                else:
                    return AttendanceStatus.ABSENT._value_
        if student_id in self.present_students:
            return AttendanceStatus.PRESENT._value_
        else:
            return AttendanceStatus.ABSENT._value_
