import datetime
from collections import OrderedDict

from django.db.models.loading import get_model
from django.http import HttpResponse
from django.shortcuts import render_to_response, redirect, get_object_or_404
from django.contrib.auth import login

# Le viste base vanno qui.
from django.views.generic import ListView
from anagrafica.forms import ModuloStepComitato, ModuloStepCredenziali, ModuloModificaAnagrafica, ModuloModificaAvatar, \
    ModuloCreazioneDocumento, ModuloModificaPassword, ModuloModificaEmailAccesso, ModuloModificaEmailContatto, \
    ModuloCreazioneTelefono, ModuloCreazioneEstensione, ModuloCreazioneTrasferimento, ModuloCreazioneDelega, \
    ModuloDonatore, ModuloDonazione, ModuloNuovaFototessera, ModuloProfiloModificaAnagrafica
from anagrafica.forms import ModuloStepCodiceFiscale
from anagrafica.forms import ModuloStepAnagrafica

# Tipi di registrazione permessi
from anagrafica.models import Persona, Documento, Telefono, Estensione, Delega, Appartenenza
from anagrafica.permessi.applicazioni import PRESIDENTE, UFFICIO_SOCI, PERMESSI_NOMI_DICT
from anagrafica.permessi.costanti import ERRORE_PERMESSI, COMPLETO, MODIFICA, LETTURA
from autenticazione.funzioni import pagina_anonima, pagina_privata
from autenticazione.models import Utenza
from base.errori import errore_generico, errore_nessuna_appartenenza
from base.files import Zip
from base.models import Log
from base.notifiche import NOTIFICA_INVIA
from curriculum.forms import ModuloNuovoTitoloPersonale, ModuloDettagliTitoloPersonale
from curriculum.models import Titolo, TitoloPersonale
from posta.models import Messaggio
from posta.utils import imposta_destinatari_e_scrivi_messaggio
from sangue.models import Donatore, Donazione

TIPO_VOLONTARIO = 'volontario'
TIPO_ASPIRANTE = 'aspirante'
TIPO_DIPENDENTE = 'dipendente'
TIPO = (TIPO_VOLONTARIO, TIPO_ASPIRANTE, TIPO_DIPENDENTE )

# I vari step delle registrazioni
STEP_COMITATO = 'comitato'
STEP_CODICE_FISCALE = 'codice_fiscale'
STEP_ANAGRAFICA = 'anagrafica'
STEP_CREDENZIALI = 'credenziali'
STEP_FINE = 'fine'

STEP_NOMI = {
    STEP_COMITATO: 'Selezione Comitato',
    STEP_CODICE_FISCALE: 'Codice Fiscale',
    STEP_ANAGRAFICA: 'Dati anagrafici',
    STEP_CREDENZIALI: 'Credenziali',
    STEP_FINE: 'Conferma',
}

# Definisce i vari step di registrazione, in ordine, per ogni tipo di registrazione.
STEP = {
    TIPO_VOLONTARIO: [STEP_COMITATO, STEP_CODICE_FISCALE, STEP_ANAGRAFICA, STEP_CREDENZIALI, STEP_FINE],
    TIPO_ASPIRANTE: [STEP_CODICE_FISCALE, STEP_ANAGRAFICA, STEP_CREDENZIALI, STEP_FINE],
    TIPO_DIPENDENTE: [STEP_COMITATO, STEP_CODICE_FISCALE, STEP_ANAGRAFICA, STEP_CREDENZIALI, STEP_FINE],
}

MODULI = {
    STEP_COMITATO: ModuloStepComitato,
    STEP_CODICE_FISCALE: ModuloStepCodiceFiscale,
    STEP_ANAGRAFICA: ModuloStepAnagrafica,
    STEP_CREDENZIALI: ModuloStepCredenziali,
    STEP_FINE: None,
}

@pagina_anonima
def registrati(request, tipo, step=None):
    """
    La vista per tutti gli step della registrazione.
    """

    # Controlla che il tipo sia valido (/registrati/<tipo>/)
    if tipo not in TIPO:
        return redirect('/errore/')  # Altrimenti porta ad errore generico

    # Se nessuno step, assume il primo step per il tipo
    # es. /registrati/volontario/ => /registrati/volontario/comitato/
    if not step:
        step = STEP[tipo][0]
        # Ricomincia, quindi svuoto la sessione!
        request.session['registrati'] = {}

    try:
        sessione = request.session['registrati'].copy()
    except KeyError:
        sessione = {}

    lista_step = [
        # Per ogni step:
        #  nome: Il nome completo dello step (es. "Selezione Comitato")
        #  slug: Il nome per il link (es. "comitato" per /registrati/<tipo>/comitato/")
        #  completato: True se lo step e' stato completato o False se futuro o attuale
        {'nome': STEP_NOMI[x], 'slug': x,
         'completato': (STEP[tipo].index(x) < STEP[tipo].index(step)),
         'attuale': (STEP[tipo].index(x) == STEP[tipo].index(step)),
         'modulo': MODULI[x](initial=sessione) if MODULI[x] else None,
         }
        for x in STEP[tipo]
    ]

    # Controlla se e' l'ultimo step
    if STEP[tipo].index(step) == len(STEP[tipo]) - 1:
        step_successivo = None
    else:
        step_successivo = STEP[tipo][STEP[tipo].index(step) + 1]

    step_modulo = MODULI[step]

    # Se questa e' la ricezione dello step compilato
    if request.method == 'POST':
        modulo = step_modulo(request.POST)
        if modulo.is_valid():

            # TODO MEMORIZZA

            for k in modulo.data:
                sessione[k] = modulo.data[k]
            request.session['registrati'] = sessione

            return redirect("/registrati/%s/%s/" % (tipo, step_successivo,))

    else:
        if step_modulo:
            modulo = step_modulo(initial=sessione)
        else:
            modulo = None

    contesto = {
        'attuale_nome': STEP_NOMI[step],
        'attuale_slug': step,
        'lista_step': lista_step,
        'step_successivo': step_successivo,
        'tipo': tipo,
        'modulo': modulo,
    }

    return 'anagrafica_registrati_step_' + step + '.html', contesto

@pagina_anonima
def registrati_conferma(request, tipo):
    """
    Controlla che tutti i parametri siano corretti in sessione ed effettua
    la registrazione vera e propria!
    """

    # Controlla che il tipo sia valido (/registrati/<tipo>/)
    if tipo not in TIPO:
        return redirect('/errore/')  # Altrimenti porta ad errore generico

    try:
        sessione = request.session['registrati'].copy()
    except KeyError:
        sessione = {}

    print(sessione)

    dati = {}

    # Carica tutti i moduli inviati da questo tipo di registrazione
    for (k, modulo) in [(x, MODULI[x](data=sessione)) for x in STEP[tipo] if MODULI[x] is not None]:

        # Controlla nuovamente la validita'
        if not modulo.is_valid():
            raise ValueError("Errore nella validazione del sub-modulo %s" % (k, ))

        # Aggiunge tutto a "dati"
        dati.update(modulo.cleaned_data)

    # Quali di questi campi vanno nella persona?
    campi_persona = [str(x.name) for x in Persona._meta.get_fields() if not x.is_relation]
    dati_persona = {x: dati[x] for x in dati if x in campi_persona}

    # Crea la persona
    p = Persona(**dati_persona)
    p.save()

    # Associa l'utenza
    u = Utenza(persona=p, email=dati['email'])
    u.set_password(dati['password'])
    u.save()

    # Effettua il login!
    u.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, u)

    # Da' il benvenuto all'utente
    p.invia_email_benvenuto_registrazione(tipo=tipo)

    redirect_url = "/utente/"

    if tipo == TIPO_ASPIRANTE:
        #  Genera semplicemente oggetto aspirante.
        p.ottieni_o_genera_aspirante()
        redirect_url = "/aspirante/"

    elif tipo == TIPO_VOLONTARIO:
        #  Richiede appartenenza come Volontario.
        a = Appartenenza(
            inizio=modulo.cleaned_data['inizio'],
            sede=modulo.cleaned_data['sede'],
            membro=Appartenenza.VOLONTARIO,
        )
        a.save()
        a.richiedi()

    elif tipo == TIPO_DIPENDENTE:
        #  Richiede appartenenza come Dipendente.
        a = Appartenenza(
            inizio=modulo.cleaned_data['inizio'],
            sede=modulo.cleaned_data['sede'],
            membro=Appartenenza.DIPENDENTE,
        )
        a.save()
        a.richiedi()

    else:
        raise ValueError("Non so come gestire questa iscrizione.")

    return redirect(redirect_url)


@pagina_privata
def utente(request, me):
    return 'anagrafica_utente_home.html'

@pagina_privata
def utente_anagrafica(request, me):

    contesto = {
        "delegati": me.deleghe_anagrafica(),
    }

    modulo_dati = ModuloModificaAnagrafica(request.POST or None, instance=me)

    if request.POST:

        if modulo_dati.is_valid():
            modulo_dati.save()

    else:

        modulo_dati = ModuloModificaAnagrafica(instance=me)

    contesto.update({
        "modulo_dati": modulo_dati,
    })

    return 'anagrafica_utente_anagrafica.html', contesto

@pagina_privata
def utente_fotografia(request, me):
   return redirect("/utente/fotografia/avatar/")

@pagina_privata
def utente_fotografia_avatar(request, me):

    modulo_avatar = ModuloModificaAvatar(request.POST or None, request.FILES or None, instance=me)

    if request.POST:
        if modulo_avatar.is_valid():
            modulo_avatar.save()

    contesto = {
        "modulo_avatar": modulo_avatar
    }

    return 'anagrafica_utente_fotografia_avatar.html', contesto

@pagina_privata
def utente_fotografia_fototessera(request, me):

    modulo_fototessera = ModuloNuovaFototessera(request.POST or None, request.FILES or None)

    sede = me.comitato_riferimento()

    if not sede:
        return errore_nessuna_appartenenza(
            request, me, torna_url="/utente/fotografia/avatar/"
        )

    if request.POST:

        if modulo_fototessera.is_valid():

            # Ritira eventuali richieste in attesa
            if me.fototessere_pending().exists():
                for x in me.fototessere_pending():
                    x.autorizzazioni_ritira()

            # Crea la fototessera
            fototessera = modulo_fototessera.save(commit=False)
            fototessera.persona = me
            fototessera.save()

            # Richiede l'autorizzazione
            fototessera.autorizzazione_richiedi(
                richiedente=me,
                destinatario=(
                    (PRESIDENTE, sede, NOTIFICA_INVIA),
                    (UFFICIO_SOCI, sede, NOTIFICA_INVIA),
                )
            )



    contesto = {
        "modulo_fototessera": modulo_fototessera
    }

    return 'anagrafica_utente_fotografia_fototessera.html', contesto

@pagina_privata
def utente_documenti(request, me):

    Messaggio.costruisci_e_invia(
        oggetto="Oggetto del messaggio",
        modello="email_testo.html",
        corpo={
            'testo': "Ciao!",
        },
        mittente=me,
        destinatari=[me, me]
    )

    contesto = {
        "documenti": me.documenti.all()
    }

    if request.method == "POST":

        nuovo_doc = Documento(persona=me)
        modulo_aggiunta = ModuloCreazioneDocumento(request.POST, request.FILES, instance=nuovo_doc)

        if modulo_aggiunta.is_valid():
            modulo_aggiunta.save()

    else:

        modulo_aggiunta = ModuloCreazioneDocumento()

    contesto.update({"modulo_aggiunta": modulo_aggiunta})

    return 'anagrafica_utente_documenti.html', contesto


@pagina_privata
def utente_documenti_cancella(request, me, pk):

    doc = get_object_or_404(Documento, pk=pk)

    if not doc.persona == me:
        return redirect('/errore/permessi/')

    doc.delete()
    return redirect('/utente/documenti/')


@pagina_privata
def utente_documenti_zip(request, me):

    if not me.documenti.exists():
        return redirect('/utente/documenti')

    z = Zip(oggetto=me)
    for d in me.documenti.all():
        z.aggiungi_file(d.file.path)
    z.comprimi_e_salva(nome='Documenti.zip')

    return redirect(z.download_url)

@pagina_privata
def utente_storico(request, me):

    contesto = {
        "appartenenze": me.appartenenze.all(),
        "deleghe": me.deleghe.all()
    }

    return 'anagrafica_utente_storico.html', contesto

@pagina_privata
def utente_contatti(request, me):

    if request.method == "POST":

        modulo_email_accesso = ModuloModificaEmailAccesso(request.POST, instance=me.utenza)
        modulo_email_contatto = ModuloModificaEmailContatto(request.POST, instance=me)
        modulo_numero_telefono = ModuloCreazioneTelefono(request.POST)

        if modulo_email_accesso.is_valid():
            modulo_email_accesso.save()

        if modulo_email_contatto.is_valid():
            modulo_email_contatto.save()

        if modulo_numero_telefono.is_valid():
            me.aggiungi_numero_telefono(
                modulo_numero_telefono.data['numero_di_telefono'],
                modulo_numero_telefono.data['tipologia'] == modulo_numero_telefono.SERVIZIO
            )

    else:

        modulo_email_accesso = ModuloModificaEmailAccesso(instance=me.utenza)
        modulo_email_contatto = ModuloModificaEmailContatto(instance=me)
        modulo_numero_telefono = ModuloCreazioneTelefono()

    numeri = me.numeri_telefono.all()
    contesto = {
        "modulo_email_accesso": modulo_email_accesso,
        "modulo_email_contatto": modulo_email_contatto,
        "modulo_numero_telefono": modulo_numero_telefono,
        "numeri": numeri
    }

    return 'anagrafica_utente_contatti.html', contesto

@pagina_privata
def utente_contatti_cancella_numero(request, me, pk):

    tel = get_object_or_404(Telefono, pk=pk)

    if not tel.persona == me:
        return redirect('/errore/permessi/')

    tel.delete()
    return redirect('/utente/contatti/')

@pagina_privata
def utente_donazioni_profilo(request, me):

    modulo = ModuloDonatore(request.POST or None, instance=me.donatore if hasattr(me, 'donatore') else None)

    if modulo.is_valid():

        if hasattr(me, 'donatore'):
            modulo.save()

        else:
            donatore = modulo.save(commit=False)
            donatore.persona = me
            donatore.save()

    contesto = {
        "modulo": modulo
    }
    return 'anagrafica_utente_donazioni_profilo.html', contesto

@pagina_privata
def utente_donazioni_sangue(request, me):
    modulo = ModuloDonazione(request.POST or None)

    if modulo.is_valid():

        donazione = modulo.save(commit=False)
        donazione.persona = me
        donazione.save()
        donazione.richiedi()

    donazioni = me.donazioni_sangue.all()

    contesto = {
        "modulo": modulo,
        "donazioni": donazioni
    }
    return 'anagrafica_utente_donazioni_sangue.html', contesto

@pagina_privata
def utente_donazioni_sangue_cancella(request, me, pk):
    donazione = get_object_or_404(Donazione, pk=pk)
    if not donazione.persona == me:
        return redirect(ERRORE_PERMESSI)

    donazione.delete()
    return redirect("/utente/donazioni/sangue/")

@pagina_privata
def utente_estensione(request, me):
    storico = me.estensioni.all()
    if request.POST:
        modulo = ModuloCreazioneEstensione(request.POST)
        if modulo.is_valid():
            est = modulo.save(commit=False)
            if est.destinazione in me.sedi_attuali():
                modulo.add_error('destinazione', 'Sei già appartenente a questa sede.')
            elif est.destinazione in [x.destinazione for x in me.estensioni_attuali_e_in_attesa()]:
                modulo.add_error('destinazione', 'Estensione già richiesta a questa sede.')
            else:

                est.richiedente = me
                est.persona = me
                modulo.save()
                est.richiedi()
    else:
        modulo = ModuloCreazioneEstensione()
    contesto = {
        "modulo": modulo,
        "storico": storico,
        "attuali": me.estensioni_attuali()
    }
    return "anagrafica_utente_estensione.html", contesto

@pagina_privata()
def utente_estensione_termina(request, me, pk):
    estensione = get_object_or_404(Estensione, pk=pk)
    if not estensione.persona == me:
        return redirect(ERRORE_PERMESSI)
    else:
        estensione.termina()
        return redirect('/utente/estensione/')


@pagina_privata
def utente_trasferimento(request, me):
    storico = me.trasferimenti.all()
    if request.POST:
        modulo = ModuloCreazioneTrasferimento(request.POST)
        if modulo.is_valid():
            trasf = modulo.save(commit=False)
            if trasf.destinazione in me.sedi_attuali():
                modulo.add_error('destinazione', 'Sei già appartenente a questa sede.')
            else:

                trasf.persona = me
                trasf.richiedente = me
                modulo.save()
                trasf.richiedi()
    else:
        modulo = ModuloCreazioneTrasferimento()
    contesto = {
        "modulo": modulo,
        "storico": storico
    }
    return "anagrafica_utente_trasferimento.html", contesto


@pagina_privata
def profilo_messaggio(request, me, pk=None):
    persona = get_object_or_404(Persona, pk=pk)
    qs = Persona.objects.filter(pk=persona.pk)
    return imposta_destinatari_e_scrivi_messaggio(request, qs)


@pagina_privata
def strumenti_delegati(request, me):
    app_label = request.session['app_label']
    model = request.session['model']
    pk = int(request.session['pk'])
    continua_url = request.session['continua_url']
    almeno = request.session['almeno']
    delega = request.session['delega']
    oggetto = get_model(app_label, model)
    oggetto = oggetto.objects.get(pk=pk)

    modulo = ModuloCreazioneDelega(request.POST or None, initial={
        "inizio": datetime.date.today(),
    })

    if modulo.is_valid():
        d = modulo.save(commit=False)

        if oggetto.deleghe.all().filter(Delega.query_attuale().q, tipo=delega, persona=d.persona).exists():
            return errore_generico(
                request, me,
                titolo="%s è già delegato" % (d.persona.nome_completo,),
                messaggio="%s ha già una delega attuale come %s per %s" % (d.persona.nome_completo, PERMESSI_NOMI_DICT[delega], oggetto),
                torna_titolo="Torna indietro",
                torna_url="/strumenti/delegati/",
            )

        d.inizio = datetime.date.today()
        d.firmatario = me
        d.tipo = delega
        d.oggetto = oggetto
        d.save()
        d.invia_notifica_creazione()

    contesto = {
        "locazione": oggetto.locazione,
        "continua_url": continua_url,
        "almeno": almeno,
        "delega": PERMESSI_NOMI_DICT[delega],
        "modulo": modulo,
        "oggetto": oggetto,
    }

    return 'anagrafica_strumenti_delegati.html', contesto


@pagina_privata
def strumenti_delegati_termina(request, me, delega_pk=None):
    app_label = request.session['app_label']
    model = request.session['model']
    pk = int(request.session['pk'])
    continua_url = request.session['continua_url']
    almeno = request.session['almeno']
    delega = request.session['delega']
    oggetto = get_model(app_label, model)
    oggetto = oggetto.objects.get(pk=pk)

    delega = get_object_or_404(Delega, pk=delega_pk)
    if not me.permessi_almeno(delega.oggetto, COMPLETO):
        return redirect(ERRORE_PERMESSI)

    delega.fine = datetime.datetime.now()
    delega.save()
    delega.invia_notifica_terminazione(me)

    return redirect("/strumenti/delegati/")


@pagina_privata
def utente_curriculum(request, me, tipo=None):

    if not tipo:
        return redirect("/utente/curriculum/CP/")

    if tipo not in dict(Titolo.TIPO):  # Tipo permesso?
        redirect(ERRORE_PERMESSI)

    passo = 1
    tipo_display = dict(Titolo.TIPO)[tipo]
    request.session['titoli_tipo'] = tipo

    titolo_selezionato = None
    modulo = ModuloNuovoTitoloPersonale(tipo, tipo_display, request.POST or None)
    valida_secondo_form = True
    if modulo.is_valid():
        titolo_selezionato = modulo.cleaned_data['titolo']
        passo = 2
        valida_secondo_form = False

    if 'titolo_selezionato_id' in request.POST:
        titolo_selezionato = Titolo.objects.get(pk=request.POST['titolo_selezionato_id'])
        passo = 2

    if passo == 2:
        modulo = ModuloDettagliTitoloPersonale(request.POST if request.POST and valida_secondo_form else None)

        if not titolo_selezionato.richiede_data_ottenimento:
            del modulo.fields['data_ottenimento']

        if not titolo_selezionato.richiede_data_scadenza:
            del modulo.fields['data_scadenza']

        if not titolo_selezionato.richiede_luogo_ottenimento:
            del modulo.fields['luogo_ottenimento']

        if not titolo_selezionato.richiede_codice:
            del modulo.fields['codice']

        if modulo.is_valid():

            tp = modulo.save(commit=False)
            tp.persona = me
            tp.titolo = titolo_selezionato
            tp.save()

            if titolo_selezionato.richiede_conferma:
                sede_attuale = me.sedi_attuali(membro__in=Appartenenza.MEMBRO_DIRETTO).first()
                if not sede_attuale:
                    return errore_nessuna_appartenenza(
                        request, me,
                        torna_url="/utente/curriculum/%s/" % (tipo,),
                    )

                tp.autorizzazione_richiedi(
                    me,
                        ((PRESIDENTE, sede_attuale), (UFFICIO_SOCI, sede_attuale))
                )

            return redirect("/utente/curriculum/%s/?inserimento=ok" % (tipo,))

    titoli = me.titoli_personali.all().filter(titolo__tipo=tipo)

    contesto = {
        "tipo": tipo,
        "tipo_display": tipo_display,
        "passo": passo,
        "modulo": modulo,
        "titoli": titoli,
        "titolo": titolo_selezionato
    }
    return 'anagrafica_utente_curriculum.html', contesto

@pagina_privata
def utente_curriculum_cancella(request, me, pk=None):

    titolo_personale = get_object_or_404(TitoloPersonale, pk=pk)
    if not titolo_personale.persona == me:
        return redirect(ERRORE_PERMESSI)

    tipo = titolo_personale.titolo.tipo
    titolo_personale.delete()

    return redirect("/utente/curriculum/%s/" % (tipo,))


def _profilo_anagrafica(request, me, persona):
    puo_modificare = me.permessi_almeno(persona, MODIFICA)
    modulo = ModuloProfiloModificaAnagrafica(request.POST or None, instance=persona)
    if puo_modificare and modulo.is_valid():
        Log.registra_modifiche(me, modulo)
        modulo.save()
    contesto = {
        "modulo": modulo,
    }
    return 'anagrafica_profilo_anagrafica.html', contesto


def _profilo_appartenenze(request, me, persona):
    return 'anagrafica_profilo_appartenenze.html', {}


def _profilo_deleghe(request, me, persona):
    return 'anagrafica_profilo_deleghe.html', {}


def _profilo_curriculum(request, me, persona):
    contesto = {
        "modulo": None
    }
    return 'anagrafica_profilo_curriculum.html', contesto


def _profilo_documenti(request, me, persona):
    puo_modificare = me.permessi_almeno(persona, MODIFICA)
    modulo = ModuloCreazioneDocumento(request.POST or None, request.FILES or None)
    if puo_modificare and modulo.is_valid():
        f = modulo.save(commit=False)
        f.persona = persona
        f.save()

    contesto = {
        "modulo": modulo,
    }
    return 'anagrafica_profilo_documenti.html', contesto

@pagina_privata
def profilo_documenti_cancella(request, me, pk, documento_pk):
    persona = get_object_or_404(Persona, pk=pk)
    documento = get_object_or_404(Documento, pk=documento_pk)
    if (not me.permessi_almeno(persona, MODIFICA)) or not (documento.persona == persona):
        print("NONONO")
        return redirect(ERRORE_PERMESSI)
    documento.delete()
    return redirect("/profilo/%d/documenti/" % (persona.pk,))


def _sezioni_profilo(puo_leggere, puo_modificare):
    r = (
        # (path, (
        #   nome, icona, _funzione, permesso?,
        # ))
        ('anagrafica', (
            'Anagrafica', 'fa-edit', _profilo_anagrafica, puo_leggere
        )),
        ('appartenenze', (
            'Appartenenze', 'fa-clock-o', _profilo_appartenenze, puo_leggere
        )),
        ('deleghe', (
            'Deleghe', 'fa-clock-o', _profilo_deleghe, puo_leggere
        )),
        ('documenti', (
            'Documenti', 'fa-folder', _profilo_documenti, puo_leggere
        )),
        ('curriculum', (
            'Curriculum', 'fa-list', _profilo_curriculum, puo_leggere
        )),
        ('sangue', (
            'Sangue', 'fa-flask', _profilo_documenti, puo_leggere
        )),
        ('quote', (
            'Quote', 'fa-money', _profilo_documenti, puo_leggere
        )),
        ('provvedimenti', (
            'Provvedimenti', 'fa-legal', _profilo_documenti, puo_leggere
        )),
        ('credenziali', (
            'Credenziali', 'fa-key', _profilo_documenti, puo_leggere
        )),
    )
    return (x for x in r if len(x[1]) < 4 or x[1][3] == True)

@pagina_privata
def profilo(request, me, pk, sezione=None):
    persona = get_object_or_404(Persona, pk=pk)
    puo_modificare = me.permessi_almeno(persona, MODIFICA)
    puo_leggere = me.permessi_almeno(persona, LETTURA)
    sezioni = OrderedDict(_sezioni_profilo(puo_leggere, puo_modificare))

    contesto = {
        "persona": persona,
        "puo_modificare": puo_modificare,
        "puo_leggere": puo_leggere,
        "sezioni": sezioni,
        "attuale": sezione,
    }

    if not sezione:  # Prima pagina
        return 'anagrafica_profilo_profilo.html', contesto

    else:  # Sezione aperta

        if sezione not in sezioni:
            return redirect(ERRORE_PERMESSI)

        s = sezioni[sezione]

        f_template, f_contesto = s[2](request, me, persona)
        contesto.update(f_contesto)
        return f_template, contesto
