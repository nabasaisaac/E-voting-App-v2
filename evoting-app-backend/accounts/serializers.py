from datetime import date, datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.models import VoterProfile
from elections.models import VotingStation

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "full_name", "role", "is_active", "is_verified", "date_joined",
            "password",
        ]
        read_only_fields = ["id", "date_joined"]
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def get_full_name(self, obj):
        return obj.first_name + " " + obj.last_name


class VoterProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    age = serializers.ReadOnlyField()
    station_name = serializers.CharField(source="station.name", read_only=True, default=None)

    class Meta:
        model = VoterProfile
        fields = [
            "id", "user", "national_id", "voter_card_number", "date_of_birth",
            "age", "gender", "address", "phone", "station", "station_name",
        ]
        read_only_fields = ["id"]


class AdminLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class VoterLoginSerializer(serializers.Serializer):
    voter_card_number = serializers.CharField(max_length=12)
    password = serializers.CharField()


class VoterRegistrationSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200)
    national_id = serializers.CharField(max_length=50)
    date_of_birth = serializers.DateField()
    gender = serializers.ChoiceField(choices=VoterProfile.Gender.choices)
    address = serializers.CharField()
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField()
    station_id = serializers.IntegerField()
    password = serializers.CharField(min_length=6, write_only=True)
    confirm_password = serializers.CharField(min_length=6, write_only=True)

    def validate_national_id(self, value):
        if VoterProfile.objects.filter(national_id=value).exists():
            raise serializers.ValidationError("A voter with this National ID already exists.")
        return value

    def validate_date_of_birth(self, value):
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18:
            raise serializers.ValidationError(
                "You must be at least 18 years old."
            )
        return value

    def validate_station_id(self, value):
        if not VotingStation.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError("Invalid or inactive voting station.")
        return value

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError("Passwords do not match.")
        return data


class AdminCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    full_name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=[
        User.Role.SUPER_ADMIN,
        User.Role.ELECTION_OFFICER,
        User.Role.STATION_MANAGER,
        User.Role.AUDITOR,
        User.Role.VOTER,
    ])
    password = serializers.CharField(min_length=6, write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists.")
        return value


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=6, write_only=True)
    confirm_password = serializers.CharField(min_length=6, write_only=True)

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data


class VoterListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    voter_card_number = serializers.CharField(source="voter_profile.voter_card_number")
    station_id = serializers.IntegerField(source="voter_profile.station_id")
    age = serializers.ReadOnlyField(source="voter_profile.age")
    gender = serializers.CharField(source="voter_profile.gender")
    national_id = serializers.CharField(source="voter_profile.national_id")

    class Meta:
        model = User
        fields = [
            "id", "full_name", "voter_card_number", "national_id",
            "station_id", "age", "gender", "is_verified", "is_active",
        ]

    def get_full_name(self, obj):
        return obj.get_full_name()


class AdminListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "full_name", "email", "role", "is_active", "date_joined"]

    def get_full_name(self, obj):
        return obj.first_name + " " + obj.last_name