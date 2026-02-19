from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import random
from datetime import date, time, datetime
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta # Certifique-se de ter este import
import json  # <--- ADICIONE ESTE PARA RESOLVER

from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy

from .forms import RegisterForm, DepositForm, WithdrawalForm, BankDetailsForm
from .models import PlatformSettings, CustomUser, Level, UserLevel, BankDetails, Deposit, Withdrawal, Task, PlatformBankDetails, Roulette, PromoCode, PromoCodeUsage

# --- ADICIONE ESTA CLASSE LOGO ABAIXO DOS IMPORTS ---
class MyPasswordChangeView(PasswordChangeView):
    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('change_password_done')
    
# --- FUNÇÃO HOME ---
def home(request):
    if request.user.is_authenticated:
        return redirect('menu')
    else:
        return redirect('cadastro')

# --- FUNÇÃO MENU ---
@login_required
def menu(request):
    user = request.user
    active_level = UserLevel.objects.filter(user=user, is_active=True).first()
    approved_deposit_total = Deposit.objects.filter(user=user, is_approved=True).aggregate(Sum('amount'))['amount__sum'] or 0
    today = date.today()
    daily_income = Task.objects.filter(user=user, completed_at__date=today).aggregate(Sum('earnings'))['earnings__sum'] or 0
    total_withdrawals = Withdrawal.objects.filter(user=user, status='Aprovado').aggregate(Sum('amount'))['amount__sum'] or 0

    try:
        platform_settings = PlatformSettings.objects.first()
        whatsapp_link = platform_settings.whatsapp_link
    except (PlatformSettings.DoesNotExist, AttributeError):
        whatsapp_link = '#'

    context = {
        'user': user,
        'active_level': active_level,
        'approved_deposit_total': approved_deposit_total,
        'daily_income': daily_income,
        'total_withdrawals': total_withdrawals,
        'whatsapp_link': whatsapp_link,
    }
    return render(request, 'menu.html', context)

# --- CADASTRO ---
def cadastro(request):
    invite_code_from_url = request.GET.get('invite', None)
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.available_balance = 0 
            
            invited_by_code = form.cleaned_data.get('invited_by_code')
            if invited_by_code:
                try:
                    invited_by_user = CustomUser.objects.get(invite_code=invited_by_code)
                    user.invited_by = invited_by_user
                except CustomUser.DoesNotExist:
                    messages.error(request, 'Código de convite inválido.')
                    return render(request, 'cadastro.html', {'form': form})
            
            user.save()
            login(request, user)
            messages.success(request, 'Cadastro realizado com sucesso!')
            return redirect('menu')
    else:
        form = RegisterForm(initial={'invited_by_code': invite_code_from_url}) if invite_code_from_url else RegisterForm()
    
    try:
        whatsapp_link = PlatformSettings.objects.first().whatsapp_link
    except (PlatformSettings.DoesNotExist, AttributeError):
        whatsapp_link = '#'
    return render(request, 'cadastro.html', {'form': form, 'whatsapp_link': whatsapp_link})

def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('menu')
    else:
        form = AuthenticationForm()
    try:
        whatsapp_link = PlatformSettings.objects.first().whatsapp_link
    except (PlatformSettings.DoesNotExist, AttributeError):
        whatsapp_link = '#'
    return render(request, 'login.html', {'form': form, 'whatsapp_link': whatsapp_link})

@login_required
def user_logout(request):
    logout(request)
    return redirect('menu')

# --- DEPÓSITO ---
@login_required
def deposito(request):
    platform_bank_details = PlatformBankDetails.objects.all()
    platform_settings = PlatformSettings.objects.first()
    deposit_instruction = platform_settings.deposit_instruction if platform_settings else 'Instruções não disponíveis.'
    
    level_deposits = Level.objects.all().values_list('deposit_value', flat=True).distinct().order_by('deposit_value')
    level_deposits_list = [str(d) for d in level_deposits] 

    if request.method == 'POST':
        form = DepositForm(request.POST, request.FILES)
        payment_method = request.POST.get('payment_method', 'bank')
        payer_name = request.POST.get('payer_name', '')

        if form.is_valid():
            deposit = form.save(commit=False)
            deposit.user = request.user
            deposit.payment_method = payment_method
            deposit.payer_name = payer_name
            deposit.save()
            
            return render(request, 'deposito.html', {
                'platform_bank_details': platform_bank_details,
                'deposit_instruction': deposit_instruction,
                'level_deposits_list': level_deposits_list,
                'deposit_success': True 
            })
        else:
            messages.error(request, 'Erro ao enviar o depósito. Verifique os campos.')
    
    form = DepositForm()
    context = {
        'platform_bank_details': platform_bank_details,
        'deposit_instruction': deposit_instruction,
        'form': form,
        'level_deposits_list': level_deposits_list,
        'deposit_success': False,
    }
    return render(request, 'deposito.html', context)

@login_required
def approve_deposit(request, deposit_id):
    if not request.user.is_staff:
        return redirect('menu')
    deposit = get_object_or_404(Deposit, id=deposit_id)
    if not deposit.is_approved:
        deposit.is_approved = True
        deposit.save()
        
        deposit.user.available_balance += deposit.amount
        deposit.user.save()
        messages.success(request, f'Depósito de {deposit.amount} aprovado para {deposit.user.phone_number}.')
    return redirect('renda')

# --- SAQUE ---
@login_required
def saque(request):
    MIN_WITHDRAWAL_AMOUNT = 2000
    platform_settings = PlatformSettings.objects.first()
    withdrawal_instruction = platform_settings.withdrawal_instruction if platform_settings else ''
    withdrawal_records = Withdrawal.objects.filter(user=request.user).order_by('-created_at')
    
    now = timezone.localtime(timezone.now())
    today = now.date()
    weekday = now.weekday() 

    is_sunday = (weekday == 6)
    is_business_hours = (9 <= current_hour < 17) if 'current_hour' in locals() else (9 <= now.hour < 17)
    is_business_day = (0 <= weekday <= 5)
    is_time_to_withdraw = is_business_hours and is_business_day and not is_sunday

    withdrawals_today_count = Withdrawal.objects.filter(
        user=request.user, 
        created_at__date=today, 
        status__in=['Pendente', 'Aprovado']
    ).count()
    can_withdraw_today = withdrawals_today_count == 0

    if request.method == 'POST':
        form = WithdrawalForm(request.POST)
        
        metodo = request.POST.get('withdrawal_method')
        bank_name = request.POST.get('bank_name')
        iban = request.POST.get('iban')
        holder = request.POST.get('account_holder')
        pix_key = request.POST.get('pix_key')
        usdt_addr = request.POST.get('usdt_address')
        
        if form.is_valid():
            original_amount = form.cleaned_data['amount']
            
            if is_sunday:
                messages.error(request, 'Hoje é feriado, saque é só amanhã.')
            elif not is_business_hours:
                messages.error(request, 'O sistema de saque só funciona das 09:00 às 17:00.')
            elif not can_withdraw_today:
                messages.error(request, 'Você já realizou um saque hoje. Tente novamente amanhã.')
            elif original_amount < MIN_WITHDRAWAL_AMOUNT:
                messages.error(request, f'O valor mínimo para levantamento é {MIN_WITHDRAWAL_AMOUNT} Kz.')
            elif request.user.available_balance < original_amount:
                messages.error(request, 'Saldo insuficiente para esta operação.')
            elif not metodo:
                messages.error(request, 'Selecione um método de levantamento.')
            else:
                taxa = original_amount * Decimal('0.10')
                amount_with_discount = original_amount - taxa
                
                detalhes = f"Método: {metodo} | Taxa de 10% descontada: {taxa} KZ | "
                if metodo == 'BANCO':
                    detalhes += f"Banco: {bank_name}, IBAN: {iban}, Titular: {holder}"
                elif metodo == 'PIX':
                    detalhes += f"Chave: {pix_key}"
                elif metodo == 'USDT':
                    detalhes += f"Carteira: {usdt_addr}"

                Withdrawal.objects.create(
                    user=request.user, 
                    amount=amount_with_discount,
                    method=metodo,
                    withdrawal_details=detalhes,
                    status='Pendente'
                )

                request.user.available_balance -= original_amount
                request.user.save()
                
                messages.success(request, f'Pedido enviado! Taxa de 10% descontada ({taxa} KZ). Você receberá {amount_with_discount} KZ.')
                return redirect('saque')
    else:
        form = WithdrawalForm()

    context = {
        'withdrawal_instruction': withdrawal_instruction,
        'withdrawal_records': withdrawal_records,
        'form': form,
        'is_time_to_withdraw': is_time_to_withdraw,
        'is_sunday': is_sunday,
        'MIN_WITHDRAWAL_AMOUNT': MIN_WITHDRAWAL_AMOUNT,
        'can_withdraw_today': can_withdraw_today,
    }
    return render(request, 'saque.html', context)
    
    # --- TAREFAS (LOGICA ATUALIZADA) ---
@login_required
def tarefa(request):
    user = request.user
    active_level = UserLevel.objects.filter(user=user, is_active=True).first()
    is_estagiario = active_level is None
    today = timezone.localdate()
    tasks_completed_today = Task.objects.filter(user=user, completed_at__date=today).count()
    
    # Validação de Domingo para o template
    is_sunday = (today.weekday() == 6)

    # Lista de empresas enviada diretamente para o template para (resolve o erro de TemplateTag)
    companies = [
        {'name': 'UNITEL', 'category': 'Telecomunicações', 'icon': 'fa-phone'},
        {'name': 'SONANGOL', 'category': 'Energia', 'icon': 'fa-gas-pump'},
        {'name': 'BANCO BAI', 'category': 'Finanças', 'icon': 'fa-building-columns'},
        {'name': 'TAAG', 'category': 'Aviação', 'icon': 'fa-plane'},
        {'name': 'ZAP', 'category': 'Entretenimento', 'icon': 'fa-tv'},
        {'name': 'CANDANDO', 'category': 'Retalho', 'icon': 'fa-cart-shopping'},
        {'name': 'ENSA', 'category': 'Seguros', 'icon': 'fa-shield-halved'},
        {'name': 'AFRICEL', 'category': 'Telecomunicações', 'icon': 'fa-tower-cell'},
        {'name': 'KERO', 'category': 'Supermercado', 'icon': 'fa-basket-shopping'},
        {'name': 'NOSSA SEGUROS', 'category': 'Seguros', 'icon': 'fa-file-contract'},
    ]
    
    context = {
        'is_estagiario': is_estagiario,
        'active_level': active_level,
        'tasks_completed_today': tasks_completed_today,
        'max_tasks': 1,
        'is_sunday': is_sunday,
        'free_days_count': user.free_days_count,
        'companies': companies,
    }
    return render(request, 'tarefa.html', context)

@login_required
@require_POST
def process_task(request):
    user = request.user
    now = timezone.localtime(timezone.now())
    today = now.date()
    weekday = now.weekday()

    # 1. BLOQUEIO DE DOMINGO
    if weekday == 6:
        return JsonResponse({'success': False, 'message': 'Hoje é feriado, volte amanhã.'})

    # 2. LIMITE DIÁRIO
    if Task.objects.filter(user=user, completed_at__date=today).exists():
        return JsonResponse({'success': False, 'message': 'Limite diário de tarefas alcançado.'})

    try:
        active_user_level = UserLevel.objects.filter(user=user, is_active=True).select_related('level').first()

        if active_user_level:
            # Usuário com Plano Pago
            task_earnings = Decimal(str(active_user_level.level.daily_gain))
        else:
            # LOGICA DE ESTAGIÁRIO
            if user.free_days_count >= 2:
                return JsonResponse({
                    'success': False, 
                    'message': 'Seu período de estagiário terminou. Adquira um plano pago para continuar.'
                })
            
            task_earnings = Decimal('450.00') # Ganho de estagiário
            user.free_days_count += 1

        # Salva a tarefa e atualiza saldo
        Task.objects.create(user=user, earnings=task_earnings, completed_at=now) 
        user.available_balance += task_earnings
        user.save()

        # Comissões de rede (Apenas para planos pagos)
        p1 = user.invited_by
        if active_user_level and p1: 
            subsidy_a = task_earnings * Decimal('0.20')
            p1.available_balance += subsidy_a
            p1.subsidy_balance += subsidy_a
            p1.save()

            p2 = p1.invited_by
            if p2:
                subsidy_b = task_earnings * Decimal('0.03')
                p2.available_balance += subsidy_b
                p2.subsidy_balance += subsidy_b
                p2.save()

                p3 = p2.invited_by
                if p3:
                    subsidy_c = task_earnings * Decimal('0.02')
                    p3.available_balance += subsidy_c
                    p3.subsidy_balance += subsidy_c
                    p3.save()

        return JsonResponse({
            'success': True, 
            'message': f'Tarefa concluída! {task_earnings} KZ adicionados ao seu saldo.'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro: {str(e)}'})
        
@login_required
def nivel(request):
    if request.method == 'POST':
        level_id = request.POST.get('level_id')
        level_to_buy = get_object_or_404(Level, id=level_id)
        val = level_to_buy.deposit_value

        user_levels = UserLevel.objects.filter(user=request.user, is_active=True).values_list('level__id', flat=True)
        if level_to_buy.id in user_levels:
            messages.error(request, 'Você já possui este nível ativo.')
            return redirect('nivel')

        if request.user.available_balance >= val:
            request.user.available_balance -= val
            UserLevel.objects.create(user=request.user, level=level_to_buy, is_active=True)
            request.user.level_active = True
            request.user.save()

            p1 = request.user.invited_by
            if p1 and UserLevel.objects.filter(user=p1, is_active=True).exists():
                com1 = val * Decimal('0.15')
                p1.available_balance += com1
                p1.subsidy_balance += com1
                p1.save()

                p2 = p1.invited_by
                if p2 and UserLevel.objects.filter(user=p2, is_active=True).exists():
                    com2 = val * Decimal('0.03')
                    p2.available_balance += com2
                    p2.subsidy_balance += com2
                    p2.save()

                    p3 = p2.invited_by
                    if p3 and UserLevel.objects.filter(user=p3, is_active=True).exists():
                        com3 = val * Decimal('0.01')
                        p3.available_balance += com3
                        p3.subsidy_balance += com3
                        p3.save()

            messages.success(request, f'Parabéns! Nível {level_to_buy.name} ativado com sucesso!')
        else:
            messages.error(request, 'Saldo insuficiente para ativar este nível.')
        return redirect('nivel')
    
    active_user_levels = UserLevel.objects.filter(user=request.user, is_active=True).values_list('level__id', flat=True)
    context = {
        'levels': Level.objects.all().order_by('deposit_value'),
        'user_levels': active_user_levels,
    }
    return render(request, 'nivel.html', context)

# --- EQUIPA ---
@login_required
def equipa(request):
    user = request.user
    level_a = CustomUser.objects.filter(invited_by=user)
    level_b = CustomUser.objects.filter(invited_by__in=level_a)
    level_c = CustomUser.objects.filter(invited_by__in=level_b)

    context = {
        'team_count': level_a.count() + level_b.count() + level_c.count(),
        'total_investors': (level_a.filter(userlevel__is_active=True).distinct().count() + 
                           level_b.filter(userlevel__is_active=True).distinct().count() + 
                           level_c.filter(userlevel__is_active=True).distinct().count()),
        'invite_link': request.build_absolute_uri(reverse('cadastro')) + f'?invite={user.invite_code}',
        'subsidy_balance': user.subsidy_balance,
        'level_a_count': level_a.count(),
        'level_a_investors': level_a.filter(userlevel__is_active=True).distinct().count(),
        'level_b_count': level_b.count(),
        'level_b_investors': level_b.filter(userlevel__is_active=True).distinct().count(),
        'level_c_count': level_c.count(),
        'level_c_investors': level_c.filter(userlevel__is_active=True).distinct().count(),
        'level_a': level_a,
        'level_b': level_b,
        'level_c': level_c,
    }
    return render(request, 'equipa.html', context)

@login_required
def sorteio_view(request):
    """
    Renderiza a página de sorteio e mostra os últimos ganhadores.
    """
    # IMPORTANTE: No models.py deve existir o modelo PromoCodeUsage que criamos
    # Se ainda não criou o modelo, use o histórico da antiga Roulette por enquanto
    try:
        from .models import PromoCodeUsage
        recent_winners = PromoCodeUsage.objects.select_related('user').order_by('-used_at')[:15]
    except ImportError:
        # Fallback caso ainda não tenha migrado o model
        recent_winners = Roulette.objects.filter(is_approved=True).order_by('-spin_date')[:15]

    return render(request, 'sorteio.html', {'recent_winners': recent_winners})

@login_required
@require_POST
def validar_codigo_sorteio(request):
    """
    Valida o código inserido, distribui o saldo e subsídio, e bloqueia uso repetido no dia.
    """
    try:
        from .models import PromoCode, PromoCodeUsage
        data = json.loads(request.body)
        input_code = data.get('code', '').strip().upper()
        user = request.user
        today = timezone.localdate()

        # 1. Validação de segurança: Um código por dia por usuário
        ja_usou_hoje = PromoCodeUsage.objects.filter(user=user, used_at__date=today).exists()
        if ja_usou_hoje:
            return JsonResponse({
                'success': False, 
                'message': 'Você já participou do sorteio hoje. Volte amanhã!'
            })

        # 2. Verifica se o código existe no sistema e está ativo
        try:
            promo = PromoCode.objects.get(code=input_code, is_active=True)
        except PromoCode.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'message': 'Código inválido ou expirado.'
            })

        # 3. LÓGICA DE GANHO (OBEDIENTE: SALDO + SUBSÍDIO)
        prize_amount = promo.value
        
        user.available_balance += prize_amount
        user.subsidy_balance += prize_amount
        user.save()

        # 4. Registra no histórico de usos
        PromoCodeUsage.objects.create(
            user=user, 
            promo_code=promo, 
            prize_won=prize_amount
        )

        # 5. Também registra na tabela antiga de Roleta para manter compatibilidade de histórico se desejar
        Roulette.objects.create(user=user, prize=prize_amount, is_approved=True)

        return JsonResponse({
            'success': True,
            'prize': str(prize_amount),
            'message': 'Código resgatado com sucesso!'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro no servidor: {str(e)}'})

# --- SOBRE E PERFIL (MANTIDOS) ---

# --- SOBRE E PERFIL ---
@login_required
def sobre(request):
    platform_settings = PlatformSettings.objects.first()
    history_text = platform_settings.history_text if platform_settings else 'Informação indisponível.'
    return render(request, 'sobre.html', {'history_text': history_text})

@login_required
def perfil(request):
    bank_details, created = BankDetails.objects.get_or_create(user=request.user)
    withdrawal_records = Withdrawal.objects.filter(user=request.user).order_by('-created_at')
    
    if request.method == 'POST':
        if 'update_bank' in request.POST:
            form = BankDetailsForm(request.POST, instance=bank_details)
            if form.is_valid():
                form.save()
                messages.success(request, 'Dados bancários atualizados com sucesso!')
                return redirect('perfil')
    
    context = {
        'form': BankDetailsForm(instance=bank_details),
        'bank_info': bank_details,
        'user_levels': UserLevel.objects.filter(user=request.user, is_active=True),
        'withdrawal_records': withdrawal_records,
    }
    return render(request, 'perfil.html', context)

@login_required
def renda(request):
    user = request.user
    today = timezone.localdate() #
    yesterday = today - timedelta(days=1) #
    
    # Datas para cálculo mensal
    first_day_current_month = today.replace(day=1) #
    last_day_last_month = first_day_current_month - timedelta(days=1) #
    first_day_last_month = last_day_last_month.replace(day=1) #

    # 1. Receita de Hoje
    receita_hoje = Task.objects.filter(
        user=user, completed_at__date=today
    ).aggregate(Sum('earnings'))['earnings__sum'] or 0 #

    # 2. Receita de Ontem
    receita_ontem = Task.objects.filter(
        user=user, completed_at__date=yesterday
    ).aggregate(Sum('earnings'))['earnings__sum'] or 0 #

    # 3. Receita deste Mês
    receita_mes_atual = Task.objects.filter(
        user=user, completed_at__date__gte=first_day_current_month
    ).aggregate(Sum('earnings'))['earnings__sum'] or 0 #

    # 4. Receita do Mês Anterior
    receita_mes_anterior = Task.objects.filter(
        user=user, 
        completed_at__date__gte=first_day_last_month,
        completed_at__date__lte=last_day_last_month
    ).aggregate(Sum('earnings'))['earnings__sum'] or 0 #

    # 5. Tarefas Concluídas Hoje (Contagem)
    tarefa_hoje_count = Task.objects.filter(
        user=user, completed_at__date=today
    ).count() #

    # 6. Total Sacado com Sucesso
    total_sacado = Withdrawal.objects.filter(
        user=user, status='Aprovado'
    ).aggregate(Sum('amount'))['amount__sum'] or 0 #

    context = {
        'user': user,
        'receita_hoje': receita_hoje,
        'receita_ontem': receita_ontem,
        'receita_mes_atual': receita_mes_atual,
        'receita_mes_anterior': receita_mes_anterior,
        'tarefa_hoje_count': tarefa_hoje_count,
        'total_sacado': total_sacado,
    }
    return render(request, 'renda.html', context) #
    