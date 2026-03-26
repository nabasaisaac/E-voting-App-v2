from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from accounts.permissions import IsAdminOrReadOnlyVoter, IsAdminUser, IsVerifiedVoter
from elections.models import Poll
from voting.serializers import CastVoteSerializer
from voting.services import (
    ResultsService,
    StatisticsService,
    VoteCastingService,
    VoteHistoryService,
)


class OpenPollsView(APIView):
    permission_classes = [IsVerifiedVoter]

    def get(self, request):
        voter = request.user
        station_id = voter.voter_profile.station_id

        polls = Poll.objects.filter(
            status=Poll.Status.OPEN,
            stations__id=station_id,
        ).prefetch_related(
            "poll_positions__position",
            "poll_positions__candidates",
        )

        voted_poll_ids = set(
            voter.votes_cast.values_list("poll_id", flat=True).distinct()
        )

        data = []
        for poll in polls:
            positions = []
            for pp in poll.poll_positions.all():
                candidates = [
                    {
                        "id": c.id,
                        "full_name": c.full_name,
                        "party": c.party,
                        "age": c.age,
                        "education": c.get_education_display(),
                        "years_experience": c.years_experience,
                        "manifesto": c.manifesto,
                    }
                    for c in pp.candidates.all()
                ]
                positions.append({
                    "poll_position_id": pp.id,
                    "position_title": pp.position.title,
                    "max_winners": pp.position.max_winners,
                    "candidates": candidates,
                })
            data.append({
                "id": poll.id,
                "title": poll.title,
                "election_type": poll.election_type,
                "start_date": str(poll.start_date),
                "end_date": str(poll.end_date),
                "has_voted": poll.id in voted_poll_ids,
                "positions": positions,
            })

        return Response(data)


class CastVoteView(APIView):
    permission_classes = [IsVerifiedVoter]
    serializer_class = CastVoteSerializer

    def post(self, request):
        serializer = CastVoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = VoteCastingService()
        try:
            votes = service.cast(request.user, serializer.validated_data)
        except Poll.DoesNotExist:
            return Response({"detail": "Poll not found."}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        vote_hash = votes[0].vote_hash if votes else ""
        return Response({
            "detail": "Your vote has been recorded successfully.",
            "vote_reference": vote_hash,
        })


class VotingHistoryView(APIView):
    permission_classes = [IsVerifiedVoter]

    def get(self, request):
        service = VoteHistoryService()
        history = service.get_voter_history(request.user)
        return Response(history)


class PollResultsView(APIView):
    permission_classes = [IsAdminOrReadOnlyVoter]

    def get(self, request, pk):
        service = ResultsService()
        try:
            results = service.get_poll_results(pk)
        except Poll.DoesNotExist:
            return Response({"detail": "Poll not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(results)


class StationResultsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        service = ResultsService()
        try:
            results = service.get_station_results(pk)
        except Poll.DoesNotExist:
            return Response({"detail": "Poll not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(results)


class ClosedPollResultsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        closed_polls = Poll.objects.filter(status=Poll.Status.CLOSED)
        service = ResultsService()
        results = []
        for poll in closed_polls:
            results.append(service.get_poll_results(poll.id))
        return Response(results)


class SystemStatisticsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        service = StatisticsService()
        return Response({
            "overview": service.get_system_overview(),
            "demographics": service.get_voter_demographics(),
            "station_load": service.get_station_load(),
            "party_distribution": service.get_party_distribution(),
            "education_distribution": service.get_education_distribution(),
        })