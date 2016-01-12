from django.contrib.admin import ModelAdmin
from django.db.models import Q

from anagrafica.models import Persona, Appartenenza
from base.utils import filtra_queryset, testo_euro
from ufficio_soci.forms import ModuloElencoSoci, ModuloElencoElettorato, ModuloElencoQuote
from datetime import date
from django.utils.timezone import now

from ufficio_soci.models import Tesseramento, Quota


class Elenco:
    """
    Rappresenta un elenco semplice di persone.
    """

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.modulo_riempito = None  # Qui andra' un eventuale modulo riempito.

    def modulo(self):
        """
        Ritorna un oggetto forms.Form da compilare.
        :return:
        """
        return None

    def risultati(self):
        """
        Dato il contenuto del modulo.
        :param modulo:
        :param args:
        :param kwargs:
        :return: Un QuerySet<Persona> con tutti i risultati.
        """
        raise NotImplementedError("Metodo risultati dell'elenco non implementato.")

    def filtra(self, queryset, termine):
        raise NotImplementedError("Metodo filtra non implementato.")

    def ordina(self, qs):
        return qs

    def excel_colonne(self):
        return ()

    def excel_foglio(self, p):
        """
        Questa funzione, data una persona, determina in quale foglio excel
         dell'elenco verra' posizionato.
        :param p: La persona.
        :return: Il nome del foglio di destinazione.
        """
        return "Foglio 1"

    def template(self):
        return 'us_elenchi_inc_vuoto.html'



class ElencoVistaSemplice(Elenco):

    def excel_colonne(self):
        return super(ElencoVistaSemplice, self).excel_colonne() + (
            ("Cognome", lambda p: p.cognome),
            ("Nome", lambda p: p.nome),
            ("Codice Fiscale", lambda p: p.codice_fiscale),
        )

    def ordina(self, qs):
        return qs.order_by('cognome', 'nome',)

    def filtra(self, queryset, termine):
        return filtra_queryset(queryset, termini_ricerca=termine,
                               campi_ricerca=['nome', 'cognome', 'codice_fiscale',])

    def template(self):
        return 'us_elenchi_inc_persone.html'


class ElencoVistaAnagrafica(ElencoVistaSemplice):
    """
    Un elenco che, esportato in excel, contiene tutti i dati
     anagrafici delle persone.
    """

    def excel_colonne(self):
        return super(ElencoVistaAnagrafica, self).excel_colonne() + (
            ("Data di Nascita", lambda p: p.data_nascita),
            ("Luogo di Nascita", lambda p: p.comune_nascita),
            ("Provincia di Nascita", lambda p: p.provincia_nascita),
            ("Stato di Nascita", lambda p: p.stato_nascita),
            ("Indirizzo di residenza", lambda p: p.indirizzo_residenza),
            ("Comune di residenza", lambda p: p.comune_residenza),
            ("Provincia di residenza", lambda p: p.provincia_residenza),
            ("Stato di residenza", lambda p: p.stato_residenza),
            ("Email", lambda p: p.email),
            ("Numeri di telefono", lambda p: ", ".join([str(x) for x in p.numeri_telefono.all()])),
        )


class ElencoVistaSoci(ElencoVistaAnagrafica):

    def template(self):
        return 'us_elenchi_inc_soci.html'

    def excel_foglio(self, p):
        if self.modulo_riempito and 'al_giorno' in self.modulo_riempito.cleaned_data \
                and self.modulo_riempito.cleaned_data['al_giorno']:
            sede = p.sede_riferimento(al_giorno=self.modulo_riempito.cleaned_data['al_giorno'])
        else:
            sede = p.sede_riferimento()

        return sede.nome if sede else 'Altro'

    def excel_colonne(self):
        return super(ElencoVistaSoci, self).excel_colonne() + (
            ("Ingresso in CRI", lambda p: p.ingresso()),
        )


class ElencoSociAlGiorno(ElencoVistaSoci):
    """
    args: QuerySet<Sede>, Sedi per le quali compilare gli elenchi soci
    """

    def risultati(self):
        qs_sedi = self.args[0]
        return Persona.objects.filter(
            Appartenenza.query_attuale(
                al_giorno=self.modulo_riempito.cleaned_data['al_giorno'],
                sede__in=qs_sedi, membro__in=Appartenenza.MEMBRO_SOCIO,
            ).via("appartenenze")
        ).prefetch_related(
            'appartenenze', 'appartenenze__sede',
            'utenza', 'numeri_telefono'
        )

    def modulo(self):
        return ModuloElencoSoci


class ElencoSostenitori(ElencoVistaAnagrafica):
    """
    args: QuerySet<Sede>, Sedi per le quali compilare gli elenchi sostenitori
    """

    def risultati(self):
        qs_sedi = self.args[0]
        return Persona.objects.filter(
            Appartenenza.query_attuale(
                sede__in=qs_sedi, membro=Appartenenza.SOSTENITORE,
            ).via("appartenenze")
        ).prefetch_related(
            'appartenenze', 'appartenenze__sede',
            'utenza', 'numeri_telefono'
        )


class ElencoVolontari(ElencoVistaSoci):
    """
    args: QuerySet<Sede>, Sedi per le quali compilare gli elenchi sostenitori
    """

    def risultati(self):
        qs_sedi = self.args[0]
        return Persona.objects.filter(
            Appartenenza.query_attuale(
                sede__in=qs_sedi, membro=Appartenenza.VOLONTARIO,
            ).via("appartenenze")
        ).prefetch_related(
            'appartenenze', 'appartenenze__sede',
            'utenza', 'numeri_telefono'
        )


class ElencoQuote(ElencoVistaSoci):
    """
    args: QuerySet<Sede> Sedi per le quali compilare gli elenchi quote associative
    """
    def modulo(self):
        return ModuloElencoQuote

    def risultati(self):
        qs_sedi = self.args[0]
        modulo = self.modulo_riempito

        try:
            tesseramento = Tesseramento.objects.get(anno=modulo.cleaned_data.get('anno'))

        except Tesseramento.DoesNotExist:  # Errore tesseramento anno non esistente
            raise ValueError("Anno di tesseramento non valido o gestito da Gaia.")

        if modulo.cleaned_data['tipo'] == modulo.VERSATE:
            origine = tesseramento.paganti()  # Persone con quote pagate

        else:
            origine = tesseramento.non_paganti()  # Persone con quote NON pagate

        # Ora filtra per Sede
        return origine.filter(
            appartenenze__sede__in=qs_sedi,
        ).prefetch_related('quote')

    def excel_colonne(self):
        anno = self.modulo_riempito.cleaned_data['anno']
        return super(ElencoQuote, self).excel_colonne() + (
            ("Importo quota", lambda p: ', '.join([testo_euro(q.importo_totale) for q in p.quote_anno(anno, stato=Quota.REGISTRATA)])),
            ("Data versamento", lambda p: ', '.join([q.data_versamento.strftime('%d/%m/%y') for q in p.quote_anno(anno, stato=Quota.REGISTRATA)])),
            ("Registrata da", lambda p: ', '.join([q.registrato_da.nome_completo for q in p.quote_anno(anno, stato=Quota.REGISTRATA)])),
        )

    def template(self):
        modulo = self.modulo_riempito
        if modulo.cleaned_data['tipo'] == modulo.VERSATE:
            return 'us_elenchi_inc_quote.html'

        return 'us_elenchi_inc_soci.html'



class ElencoOrdinari(ElencoVistaSoci):
    """
    args: QuerySet<Sede>, Sedi per le quali compilare gli elenchi sostenitori
    """

    def risultati(self):
        qs_sedi = self.args[0]
        return Persona.objects.filter(
            Appartenenza.query_attuale(
                sede__in=qs_sedi, membro=Appartenenza.ORDINARIO,
            ).via("appartenenze")
        ).prefetch_related(
            'appartenenze', 'appartenenze__sede',
            'utenza', 'numeri_telefono'
        )


class ElencoElettoratoAlGiorno(ElencoVistaSoci):
    """
    args: QuerySet<Sede>, Sedi per le quali compilare gli elenchi soci
    """

    def risultati(self):
        qs_sedi = self.args[0]

        oggi = now().date()
        nascita_minima = date(oggi.year - 18, oggi.month, oggi.day)
        anzianita_minima = date(oggi.year - Appartenenza.MEMBRO_ANZIANITA_ANNI, oggi.month, oggi.day)

        aggiuntivi = {
            # Anzianita' minima
            "appartenenze__in": Appartenenza.con_esito_ok().filter(
                membro__in=Appartenenza.MEMBRO_ANZIANITA,
                inizio__lte=anzianita_minima
            )
        }
        if self.modulo_riempito.cleaned_data['elettorato'] == ModuloElencoElettorato.ELETTORATO_PASSIVO:
            # Elettorato passivo,
            aggiuntivi.update({
                # Eta' minima
                "data_nascita__lte": nascita_minima,
            })

        return Persona.objects.filter(
            Appartenenza.query_attuale(
                al_giorno=self.modulo_riempito.cleaned_data['al_giorno'],
                sede__in=qs_sedi, membro__in=Appartenenza.MEMBRO_SOCIO,
            ).via("appartenenze"),
            Q(**aggiuntivi),
        ).prefetch_related(
            'appartenenze', 'appartenenze__sede',
            'utenza', 'numeri_telefono'
        )

    def modulo(self):
        return ModuloElencoElettorato
