from asyncio import sleep
from datetime import datetime, timedelta
import math
from os import environ as env
from os import path
from typing import Union

import nextcord
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from nextcord import (Button, ButtonStyle, ClientUser, Colour,
                      Embed, Interaction, Member, PermissionOverwrite, Role,
                      SelectOption, SlashOption, TextChannel, TextInputStyle,
                      User, slash_command, ui, utils, PartialInteractionMessage)

from nextcord.ext import commands

SCOPES = [env['SCOPES'],]
GOOGLE_CALENDAR_ID = env['GOOGLE_CALENDAR_ID']

CLIENT_ROLE = int(env['CLIENT_ROLE'])
MODERATION_ROLE = int(env['MODERATION_ROLE'])

MEETINGS_CHANNEL_ID = int(env['MEETINGS_CHANNEL_ID'])
MEETINGS_LOGS_CHANNEL_ID = int(env['MEETINGS_LOGS_CHANNEL_ID'])
OPEN_RDV_CATEGORY_ID = int(env['OPEN_RDV_CATEGORY_ID'])
ARCHIVED_RDV_CATEGORY_ID = int(env['ARCHIVED_RDV_CATEGORY_ID'])

def get_weekday(number: int) -> str:
    weekdays = {
        0: "Lundi", 
        1: "Mardi", 
        2: "Mercredi",
        3: "Jeudi", 
        4: "Vendredi", 
        5: "Samedi", 
        6: "Dimanche"
        }

    return weekdays[number]


def get_creds() -> Union[Credentials, None]:
    creds = None

    if path.exists('auth/token.json'):
        creds = Credentials.from_authorized_user_file(
                'auth/token.json', SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'auth/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
        with open('auth/token.json', 'w') as token:
            token.write(creds.to_json())

    if isinstance(creds, Credentials):
        return creds

creds = get_creds()

service = build('calendar', 'v3', credentials=creds)

def time_strp(time) -> datetime:
    time = datetime.strptime(time, '%Y-%m-%dT%H:%M:%S')
    return time


def event_strp(event) -> tuple[datetime, datetime, str, str]:
    start = event['start'].get('dateTime', event['start'].get('date'))
    offset = start[-6:]
    start = start[:-6]
    start = time_strp(start)

    end = event['end'].get('dateTime', event['end'].get('date'))
    end = end[:-6]
    end = time_strp(end)

    timezone: str = event['start'].get('timeZone')
    return start, end, offset, timezone


class CalendarEvent():
    def __init__(self, event) -> None:
        self.kind = event.get('kind', None)
        self.etag = event.get('etag', None)
        self.id = event.get('id', None)
        self.status = event.get('status', None)
        self.htmlLink = event.get('htmlLink', None)
        self.created = event.get('created', None)
        self.updated = event.get('updated', None)
        self.summary = event.get('summary', "")
        self.description = event.get('description', "")
        self.creator = event.get('creator', None)
        self.organizer = event.get('organizer', None)
        self.start, self.end, self.offset, self.timezone = event_strp(event)
        self.iCalUID = event.get('iCalUID', None)
        self.sequence = event.get('sequence', None)
        self.reminders = event.get('reminders', None)
        self.eventType = event.get('eventType', None)
        self.colorId = event.get('colorId', None)
        self.location = event.get('location', "")

    def build(self):
        event = {
            'kind': self.kind, 
            'etag': self.etag, 
            'id': self.id, 
            'status': self.status, 
            'htmlLink': self.htmlLink, 
            'created': self.created, 
            'updated': self.updated, 
            'summary': self.summary, 
            'description': self.description,
            'location': self.location, 
            'creator': self.creator,
            'organizer': self.organizer, 
            'start': {
                'dateTime': self.start.isoformat()+self.offset, 
                'timeZone': self.timezone
                }, 
            'end': {
                'dateTime': self.end.isoformat()+self.offset, 
                'timeZone': self.timezone
                }, 
            'iCalUID': self.iCalUID, 
            'sequence': self.sequence, 
            'reminders': self.reminders, 
            'eventType': self.eventType
            }

        return event


def check_event(event: CalendarEvent, arg: str = "Créneau libre") -> Union[bool, None]:
    now = datetime.utcnow()  # 'Z' indicates UTC time
    events_result = service.events().list(
        calendarId=GOOGLE_CALENDAR_ID,
        timeMin=now.isoformat() + 'Z',
        timeMax=(now + timedelta(days=7)).isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    result = None

    for i in events:
        i = CalendarEvent(i)
        if i.id == event.id:
            result = i

    if result and result.summary == arg:
        return True
    return False

def split_dispo(event: CalendarEvent) -> None:
    start = event.start
    while start + timedelta(minutes=30) <= event.end:
        slot = {
            'summary': 'Créneau libre',
            'start': {
                'dateTime': (start).isoformat(),
                'timeZone': event.timezone
            },
            'end': {
                'dateTime': (start + timedelta(minutes=30)).isoformat(),
                'timeZone': event.timezone
            }
        }
        start += timedelta(minutes=40)
        service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=slot).execute()

    service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=event.id).execute() 
            
async def get_thread_author(channel: TextChannel) -> Union[Member, User]:
    history = channel.history(oldest_first=True, limit=1)
    history_flat = await history.flatten()
    user: Union[Member, User] = history_flat[0].mentions[0]
    return user

async def close_help_thread(
    channel: TextChannel,
    channel_author: Member,
    closed_by: Union[Member, ClientUser]) -> None:
    embed_reply = Embed(
        title="This thread has now been closed",
        colour=Colour.dark_theme(),
    )

    await channel.send(embed=embed_reply)  # Send the closing message to the help thread
    await channel.set_permissions(channel_author, read_messages=False)
    # Send log
    embed_log = Embed(
        title=":x: Rendez-vous férmé",
        description=(
            f"{channel.mention}\n\nRendez vous crée par {channel_author.mention} a été férmé par {closed_by.mention}.\n\n"
            f"Createur: `{channel_author} ({channel_author.id})`\n"
            f"Férmé par: `{closed_by} ({closed_by.id})`"
        ),
        colour=0xDD2E44,  # Red
    )
    overwrites: dict[Role | Member, PermissionOverwrite] = {
        channel_author: PermissionOverwrite(view_channel=True),
    }  # type: ignore
    await channel.edit(category=utils.get(channel.guild.categories, name="Archives"), sync_permissions=True) #type: ignore
    await utils.get(channel.guild.channels, name="logs").send(embed=embed_log) #type: ignore

async def cancel_rdv(interaction: Union[Interaction, None], event: Union[CalendarEvent, None]) -> None:
    if isinstance(event, CalendarEvent):
        event.summary = "Créneau libre"
        event.description = ""
        event.location = ""
        event.reminders = {}
        
        service.events().update(calendarId=GOOGLE_CALENDAR_ID, eventId=event.id, body=event.build()).execute()  

    if isinstance(interaction, Interaction):
        embed = Embed(
                title="Rendez-vous annulé!",
                description="Le reservation a été annulé!",
                color=Colour.red()
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

class MeetingView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.dropdown: ui.Select
        self.message = None

    async def take_meeting(self, interaction: Interaction):
        for channel in interaction.channel.category.channels:  # type: ignore
            if channel.name.startswith("rendez-vous"):
                author = await get_thread_author(channel)  # type: ignore
                if author == interaction.user:
                    embed = Embed(
                        title="Vous avez déja pris un rendez-vous",
                        color=Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

        now = datetime.utcnow()  # 'Z' indicates UTC time
        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=now.isoformat() + 'Z',
            timeMax=(now + timedelta(days=7)).isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        for event in events:
            event = CalendarEvent(event)
            if event.summary.lower() == "disponible":
                split_dispo(event)

        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=now.isoformat() + 'Z',
            timeMax=(now + timedelta(days=7)).isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        slots: dict[str, list[CalendarEvent]] = {}

        for event in events:
            event = CalendarEvent(event)
            day = get_weekday(event.start.weekday())
            if event.summary == "Créneau libre":
                if day not in slots:
                    slots[day] = []
                slots[day].append(event)

        if slots:
            embed = Embed(
                title="Liste des créneaux",
                color=Colour.blue()
            )
            options: list[SelectOption] = []
            id = 1
            for day in slots:
                crens: list[str] = []
                for slot in slots[day]:
                    options.append(SelectOption(label=f"{id}", value=slot.id))
                    crens.append(
                        f"{id}. {slot.start.strftime('%H:%M')} - {slot.end.strftime('%H:%M')}")
                    id += 1
                embed.add_field(name=day, value='\n'.join(crens), inline=True)

            timeSlotsView = TimeSlotsView(options)

            self.message = await interaction.response.send_message(embed=embed, view=timeSlotsView, ephemeral=True)
        else:
            embed = Embed(
                title="Aucun créneau disponible pour le moment",
                color=Colour.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Prendre un RDV", style=ButtonStyle.primary, custom_id="meeting_view:primary")
    async def callback(self, button: ui.Button, interaction: Interaction) -> None:
        await self.take_meeting(interaction)


class TimeSlotsView(ui.View):
    def __init__(self, options):
        super().__init__()

        # Adds the dropdown to our view object.
        self.add_item(TimeSlotsDropdown(options))


class TimeSlotsDropdown(ui.Select):
    def __init__(self, options):
        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the three options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(
            placeholder="Choisissez un créneau...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: Interaction) -> None:
        event = service.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=self.values[0]).execute()
        event = CalendarEvent(event)
        if check_event(event):
            event.summary = "En cours de résérvation..." 
            event.colorId = "5"

            event = service.events().update(calendarId=GOOGLE_CALENDAR_ID, eventId=event.id, body=event.build()).execute()
            event = CalendarEvent(event)

            form = Form(event)
            await interaction.response.send_modal(form)
        else:
            embed = Embed(
                title="Le créneau que vous avez choisi n'est plus disponible",
                description="Voulez vous choisir un nouveau?",
                color=Colour.red()
            )
            retakeMeetingView = RetakeMeeting()
            await interaction.response.send_message(embed=embed, view=retakeMeetingView, ephemeral=True)
            

class Form(ui.Modal):
    def __init__(self, event: CalendarEvent):
        super().__init__("Formulaire", timeout=15)

        self.summary = ui.TextInput(
            label="Sujet du rendez-vous",
            placeholder="Définissez un sujet pour le rendez-vous",
            min_length=2,
            max_length=200,
        )
        self.add_item(self.summary)

        self.name = ui.TextInput(
            label="Chaine",
            placeholder="Nom de la chaine, et lien vers la chaine entre parentheses",
            min_length=15,
            max_length=100,
        )
        self.add_item(self.name)

        self.medias = ui.TextInput(
            label="Réseaux sociaux associés a la chaine",
            placeholder="Nom des réseaux separés par des ','",
            required=False,
            min_length=2,
            max_length=300,
        )
        self.add_item(self.medias)

        self.slots = ui.TextInput(
            label="Horaires de streaming",
            placeholder="Les horaires dans lesquels tu es en direct",
            min_length=2,
            max_length=500,
        )
        self.add_item(self.slots)

        self.description = ui.TextInput(
            label="Description de la chaine",
            style=TextInputStyle.paragraph,
            placeholder="Informations sur la chaine, jeux et concepts de la chaine et vos ambitions pour la chaine",
            max_length=1000,
        )
        self.add_item(self.description)

        self.event = event

    async def callback(self, interaction: Interaction) -> None:
        values = {
            "sujet": self.summary.value,
            "nom": self.name.value,
            "medias": self.medias.value,
            "horaires": self.slots.value,
            "description": self.description.value,
        }

        day = get_weekday(self.event.start.weekday())
        starting_time = self.event.start.strftime("%H:%M")
        ending_time = self.event.end.strftime("%H:%M")

        embed = Embed(title="Voulez vous confirmer?",
                      description=f"Etes vous sur de vouloir reserver le rendez-vous de {day} de {starting_time} a {ending_time}?",
                      color=Colour.blue())
        
        confirmView = Confirm(self.event, values)
        await interaction.response.send_message(embed=embed, view=confirmView, ephemeral=True)
        self.stop()

    async def on_timeout(self):
        print("canceling")
        await cancel_rdv(None, self.event)
        self.stop()


class Confirm(ui.View):
    def __init__(self, event: CalendarEvent, values: dict):
        super().__init__(timeout = 60)
        self.value = None
        self.event = event
        self.infos = values

    # When the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # We also send the user an ephemeral message that we're confirming their choice.
    @ui.button(label="Confirmer", style=ButtonStyle.green)
    async def confirm(self, button: ui.Button, interaction: Interaction) -> None:  
        description = ""
        for info in self.infos:
            description += f"{info}: {self.infos[info]}\n\n"

        user = interaction.user
        overwrites: dict[Role | Member, PermissionOverwrite] = {
            interaction.guild.default_role: PermissionOverwrite(view_channel=False),#type: ignore
            user: PermissionOverwrite(view_channel=True), 
            # interaction.guild.get_role(MODERATION_ROLE): PermissionOverwrite(view_channel=True)#type: ignore
        } #type: ignore

        self.event.summary = f"Rendez-vous ({user})"
        self.event.description = description
        self.event.reminders = {
                            'useDefault': False,
                            'overrides': [
                                {'method': 'popup', 'minutes': 10},
                            ], 
                            }

        if interaction.guild:
            channel = await interaction.guild.create_text_channel(name=self.event.summary, category=interaction.channel.category, overwrites=overwrites) #type: ignore
            self.event.location = channel.id
            service.events().update(calendarId=GOOGLE_CALENDAR_ID, eventId=self.event.id, body=self.event.build()).execute()

            embed = Embed(
                    title=f"Rendez-vous de {user}",
                    description=f"{get_weekday(self.event.start.weekday())} de {self.event.start.strftime('%H:%M')} a {self.event.end.strftime('%H:%M')}",
                    colour=Colour.blue(),
                )
            embed.set_footer()

            meetView = MeetView()
            msg = await channel.send(content=user.mention, view=meetView, embed=embed) #type: ignore
            await msg.pin(reason="Message principal")
            embed = Embed(
                    title="Rendez-vous pris!",
                    description="Le rendez-vous a bien été reservé!",
                    color=Colour.green()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.value = True
            self.stop()
            await meetView.schedule_alert(interaction, self.event, msg) #type: ignore
            

    # This one is similar to the confirmation button except sets the inner value to `False`
    @ui.button(label="Annuler", style=ButtonStyle.danger)
    async def cancel(self, button: ui.Button, interaction: Interaction) -> None:
        print("canceling")
        await cancel_rdv(interaction, self.event)
        self.value = False
        self.stop()

    async def on_timeout(self) -> None:
        print("timeout")
        await cancel_rdv(None, self.event)
        self.stop()


class MeetView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def schedule_alert(self, interaction: Interaction, event: CalendarEvent, message: PartialInteractionMessage) -> None:
        now = datetime.now()
        then = event.start - timedelta(minutes=10)
        wait = int((then-now).total_seconds())
        wait = 1 if wait < 0 else wait
        if interaction.guild:
            print("guild")
            await sleep(wait)
            rdv_channel = interaction.guild.get_channel(event.location)
            if str(rdv_channel.category) == "Rendez-vous":  # type: ignore
                print("category")
                if check_event(event, event.summary):
                    print("event")
                    now = datetime.now()
                    in_when = int((event.start-now).total_seconds())
                    

                    if in_when > 0:
                        embed = Embed(
                            title=f"Le rendez-vous est dans {int(math.ceil(in_when / 60))} minutes",
                            color=Colour.blue()
                        )

                        await rdv_channel.send("@here", embed=embed) #type: ignore
                        await sleep(in_when)
                else:   
                    embed = Embed(
                        title="Le rendez-vous a été annulé",
                        color=Colour.red()
                    )
                    await rdv_channel.send("@here", embed=embed)  # type: ignore

            rdv_channel = interaction.guild.get_channel(event.location)
            print(rdv_channel.category)  # type: ignore

            if str(rdv_channel.category) == "Rendez-vous":  # type: ignore
                if check_event(event, event.summary):
                        
                        embed = Embed(
                            title="Le rendez-vous a commencé",
                            color=Colour.green()
                        )

                        await rdv_channel.send("@here", embed=embed) # type: ignore
                        await sleep(10)
                        embed = Embed(
                            title="Le rendez-vous est fini",
                            color=Colour.red()
                        )

                        await rdv_channel.send("@here", embed=embed) # type: ignore
                        for button in self.children:
                            button.disabled = False  # type: ignore
                        await message.edit(view=self)  # type: ignore
                        await interaction.user.add_roles(interaction.guild.get_role(CLIENT_ROLE))  # type: ignore

                        


                else:
                    embed = Embed(
                        title="Le rendez-vous a été annulé",
                        color=Colour.red()
                    )

                    await rdv_channel.send("@here", embed=embed) #type: ignore 

    @ui.button(label="Reprendre un RDV", style=ButtonStyle.primary, custom_id=f"take_other_meet", disabled=True)
    async def take_other_meet(self, button: Button, interaction: Interaction) -> None:
        pass
    
    @ui.button(label="Fermer", style=ButtonStyle.red, custom_id=f"meet_close_button")
    async def meet_close_button(self, button: Button, interaction: Interaction) -> None:
        for children in self.children:
            children.disabled = True  # type: ignore
        await interaction.response.edit_message(view=self)
        thread_author = await get_thread_author(interaction.channel) #type: ignore
        await close_help_thread(interaction.channel, thread_author, interaction.user) #type: ignore


class RetakeMeeting(ui.View):
    def __init__(self):
        super().__init__(timeout = None)
        self.value = None

    # When the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # We also send the user an ephemeral message that we're confirming their choice.
    @ui.button(label="Confirmer", style=ButtonStyle.green)
    async def confirm(self, button: ui.Button, interaction: Interaction) -> None:
        await MeetingView().take_meeting(interaction)
        self.value = True
        self.stop()

    # This one is similar to the confirmation button except sets the inner value to `False`
    @ui.button(label="Annuler", style=ButtonStyle.danger)
    async def cancel(self, button: ui.Button, interaction: Interaction) -> None:
        await cancel_rdv(interaction, None)
        self.value = False
        self.stop()


class Meetings(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.client.loop.create_task(self.create_views())

    async def create_views(self):
        self.client.rdv_view_set = True #type: ignore
        self.client.add_view(MeetingView())
        self.client.add_view(MeetView())
    
    @slash_command(name="prepare")
    async def prepare(self, interaction: Interaction):
        meetingEmbed = Embed(title="Prise de Rendez-Vous",
                             description="Pour prendre un rendez-vous",
                             color=Colour.blue())

        await interaction.channel.purge() #type: ignore
        # type: ignore
        await interaction.channel.send(embed=meetingEmbed, view=MeetingView())

    @slash_command(name="clear", description="Pour purger le salon")
    async def clear(
            self,
            interaction: Interaction,
            channel: TextChannel = SlashOption(name="channel", description="Choisissez un salon", required=False),
            limit: int = SlashOption(name="limit", description="Choisissez une limite", required=False)) -> None:

        if not channel and isinstance(interaction.channel, TextChannel):
            channel = interaction.channel
        
        await channel.purge(limit=int(limit) if limit else None)
        
        embed = Embed(
                            title="Le salon a été purgé",
                            color=nextcord.Colour.green()
                            )

        response = await interaction.response.send_message(embed=embed)
        await sleep(5)
        await response.delete()

    @slash_command(name="clear_events", description="Pour purger le salon")
    async def clear_events(self, interaction: Interaction) -> None:
        
        events_result = service.events().list(
                                            calendarId=GOOGLE_CALENDAR_ID, 
                                            singleEvents=True, 
                                            orderBy='startTime'
                                            ).execute()
        events = events_result.get('items', [])
        deleted = []
        for event in events:
            deleted.append(event.get("summary"))
            service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=event.get("id")).execute()
            
        embed = Embed(
            title="Les events suivant ont été purgés:",
            description='\n'.join(deleted),
            color=Colour.green()
        )

        response = await interaction.response.send_message(embed=embed)
        await sleep(5)
        await response.delete()

def setup(client):
    client.add_cog(Meetings(client))
