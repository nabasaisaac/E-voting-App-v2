from datetime import date, timedelta

from django.conf import settings
from rest_framework import serializers

from elections.models import Candidate, Poll, PollPosition, Position, VotingStation


class VotingStationSerializer(serializers.ModelSerializer):
    registered_voter_count = serializers.ReadOnlyField()
    load_percentage = serializers.ReadOnlyField()

    class Meta:
        model = VotingStation
        fields = [
            "id", "name", "location", "region", "capacity", "supervisor",
            "contact", "opening_time", "closing_time", "is_active",
            "registered_voter_count", "load_percentage", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class VotingStationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = VotingStation
        fields = [
            "name", "location", "region", "capacity", "supervisor",
            "contact", "opening_time", "closing_time",
        ]

    def validate_capacity(self, value):
        if value < 1:
            raise serializers.ValidationError("Capacity must be at least 1.")
        return value


class CandidateSerializer(serializers.ModelSerializer):
    age = serializers.ReadOnlyField()
    education_display = serializers.CharField(source="get_education_display", read_only=True)

    class Meta:
        model = Candidate
        fields = [
            "id", "full_name", "national_id", "date_of_birth", "age",
            "gender", "education", "education_display", "party", "manifesto",
            "address", "phone", "email", "has_criminal_record",
            "years_experience", "is_active", "is_approved", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class CandidateCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Candidate
        fields = [
            "full_name", "national_id", "date_of_birth", "gender",
            "education", "party", "manifesto", "address", "phone",
            "email", "has_criminal_record", "years_experience",
        ]

    def validate_national_id(self, value):
        if Candidate.objects.filter(national_id=value).exists():
            raise serializers.ValidationError("A candidate with this National ID already exists.")
        return value

    def validate_date_of_birth(self, value):
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < settings.MIN_CANDIDATE_AGE:
            raise serializers.ValidationError(
                f"Candidate must be at least {settings.MIN_CANDIDATE_AGE} years old."
            )
        if age > settings.MAX_CANDIDATE_AGE:
            raise serializers.ValidationError(
                f"Candidate must not be older than {settings.MAX_CANDIDATE_AGE}."
            )
        return value

    def validate_has_criminal_record(self, value):
        if value:
            raise serializers.ValidationError(
                "Candidates with criminal records are not eligible."
            )
        return value


class CandidateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Candidate
        fields = [
            "full_name", "national_id", "party", "manifesto", "phone",
            "email", "address", "years_experience",
        ]


class PositionSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source="get_level_display", read_only=True)

    class Meta:
        model = Position
        fields = [
            "id", "title", "description", "level", "level_display",
            "max_winners", "min_candidate_age", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class PositionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = ["title", "description", "level", "max_winners", "min_candidate_age"]

    def validate_level(self, value):
        if value not in dict(Position.Level.choices):
            raise serializers.ValidationError("Invalid level.")
        return value

    def validate_max_winners(self, value):
        if value < 1:
            raise serializers.ValidationError("Must be at least 1.")
        return value


class PollPositionSerializer(serializers.ModelSerializer):
    position = PositionSerializer(read_only=True)
    candidates = CandidateSerializer(many=True, read_only=True)

    class Meta:
        model = PollPosition
        fields = ["id", "position", "candidates"]


class PollSerializer(serializers.ModelSerializer):
    poll_positions = PollPositionSerializer(many=True, read_only=True)
    total_votes_cast = serializers.ReadOnlyField()
    station_ids = serializers.PrimaryKeyRelatedField(
        source="stations", many=True, read_only=True
    )

    class Meta:
        model = Poll
        fields = [
            "id", "title", "description", "election_type", "start_date",
            "end_date", "status", "station_ids", "poll_positions",
            "total_votes_cast", "created_at",
        ]
        read_only_fields = ["id", "status", "created_at"]


class PollCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300)
    description = serializers.CharField(required=False, default="")
    election_type = serializers.ChoiceField(choices=Poll.ElectionType.choices)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    position_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)
    station_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)

    def validate_position_ids(self, value):
        # Prevent duplicate IDs which can cause confusing UI/assignment behavior and wasted DB work.
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate position IDs are not allowed.")
        # Basic abuse guard to avoid extreme payload sizes.
        if len(value) > 100:
            raise serializers.ValidationError("Too many positions supplied.")
        return value

    def validate_station_ids(self, value):
        # Prevent duplicate IDs and reduce potential for accidental over-allocation.
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate station IDs are not allowed.")
        # Basic abuse guard to avoid extreme payload sizes.
        if len(value) > 500:
            raise serializers.ValidationError("Too many stations supplied.")
        return value

    def validate(self, data):
        if data["end_date"] < data["start_date"]:
            raise serializers.ValidationError({"end_date": "End date must be after start date."})
        invalid_positions = set(data["position_ids"]) - set(
            Position.objects.filter(
                pk__in=data["position_ids"],
                is_active=True,
            ).values_list("pk", flat=True)
        )
        if invalid_positions:
            raise serializers.ValidationError(
                {"position_ids": f"Invalid or inactive positions: {invalid_positions}"}
            )
        invalid_stations = set(data["station_ids"]) - set(
            VotingStation.objects.filter(
                pk__in=data["station_ids"], is_active=True
            ).values_list("pk", flat=True)
        )
        if invalid_stations:
            raise serializers.ValidationError(
                {"station_ids": f"Invalid or inactive stations: {invalid_stations}"}
            )

        overlaps = (
            # Scheduling conflict rule: avoid having multiple draft/open polls active for the same station(s)
            # during overlapping date ranges.
            Poll.objects.filter(
                stations__in=data["station_ids"],
                start_date__lte=data["end_date"],
                end_date__gte=data["start_date"],
                status__in=[Poll.Status.DRAFT, Poll.Status.OPEN],
            )
            .distinct()
            .exists()
        )
        if overlaps:
            raise serializers.ValidationError(
                {"detail": "Another draft/open poll overlaps these dates for one or more selected stations."}
            )
        return data


class PollUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Poll
        fields = ["title", "description", "election_type", "start_date", "end_date"]


class AssignCandidatesSerializer(serializers.Serializer):
    poll_position_id = serializers.IntegerField()
    candidate_ids = serializers.ListField(child=serializers.IntegerField())

    def validate_candidate_ids(self, value):
        existing = set(
            Candidate.objects.filter(pk__in=value, is_active=True)
            .values_list("pk", flat=True)
        )
        invalid = set(value) - existing
        if invalid:
            raise serializers.ValidationError(f"Invalid or ineligible candidates: {invalid}")
        return value