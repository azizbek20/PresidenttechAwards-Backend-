# Clean Code, SOLID, DRY, KISS — Kotlin/Android uchun qo'llanma

> Bu faylni AI kodlash yordamchisi (Claude, Copilot va h.k.) uchun **system prompt** yoki jamoaviy **coding guideline** sifatida ishlatishingiz mumkin. Har qanday kod yozilganda yoki review qilinganda quyidagi qoidalarga rioya qilinsin.

---

## 1. Umumiy tamoyil

Kod **odamlar uchun** yoziladi, kompyuter uchun emas. Kompyuter har qanday kodni bajaraveradi, lekin insonlar uni o'qishi, tushunishi va o'zgartirishi kerak. Shu sababli:

- Kod o'z-o'zini tushuntirsin (self-documenting)
- Nom va tuzilma niyatni ochiq ko'rsatsin
- Sodda yechim murakkabidan doim ustun

---

## 2. Clean Code asoslari

### 2.1 Nomlash (Naming)
- O'zgaruvchi, funksiya, klass nomlari **nima qilishini/nima ekanligini** aniq ifodalasin
- Qisqartmalardan qoching: `usrRepo` emas — `userRepository`
- Boolean qiymatlar `is`, `has`, `can` bilan boshlansin: `isLoading`, `hasPermission`
- Funksiya nomi fe'l bilan boshlansin: `fetchUserData()`, `validateInput()`

```kotlin
// Yomon
fun calc(a: Int, b: Int): Int

// Yaxshi
fun calculateTotalPrice(quantity: Int, unitPrice: Int): Int
```

### 2.2 Funksiyalar
- Bitta funksiya — **bitta ish**. Agar funksiya nomi "va" so'zi bilan tavsiflansa (masalan "userni saqlaydi va email yuboradi"), uni ikkiga bo'ling
- Funksiya imkon qadar qisqa bo'lsin (odatda 20 qatordan kam)
- Parametrlar soni 3 tadan oshsa — data class yoki parameter object ishlating
- Chuqur ichma-ich `if`/`for` bloklaridan qoching (early return ishlating)

```kotlin
// Yomon
fun processOrder(order: Order) {
    if (order.isValid) {
        if (order.items.isNotEmpty()) {
            if (order.user.isActive) {
                // ...
            }
        }
    }
}

// Yaxshi — early return (guard clauses)
fun processOrder(order: Order) {
    if (!order.isValid) return
    if (order.items.isEmpty()) return
    if (!order.user.isActive) return
    // asosiy logika
}
```

### 2.3 Kommentariyalar
- Kommentariya **"nima"** emas, **"nega"**ni tushuntirishi kerak
- Agar kod tushunarsiz bo'lsa — kommentariya emas, kodni refaktor qiling
- Eskirgan yoki noto'g'ri kommentariyalarni darhol o'chiring

### 2.4 Xatoliklarni boshqarish
- Xatolarni yashirmang, `try/catch` ichida bo'sh blok qoldirmang
- Kotlin'da `sealed class` yoki `Result<T>` bilan aniq xato holatlarini ifodalang

```kotlin
sealed class NetworkResult<out T> {
    data class Success<T>(val data: T) : NetworkResult<T>()
    data class Error(val message: String) : NetworkResult<Nothing>()
}
```

---

## 3. SOLID tamoyillari

### S — Single Responsibility Principle (Yagona majburiyat)
Har bir klass faqat **bitta** o'zgarish sababiga ega bo'lishi kerak.

```kotlin
// Yomon: UI, biznes-logika va DB bitta klassda
class UserManager {
    fun saveUserToDb(user: User) { /* ... */ }
    fun showUserOnScreen(user: User) { /* ... */ }
    fun validateEmail(email: String): Boolean { /* ... */ }
}

// Yaxshi: har biri o'z vazifasida
class UserRepository { fun save(user: User) { /* ... */ } }
class UserValidator { fun validateEmail(email: String): Boolean { /* ... */ } }
class UserViewModel { /* faqat UI holatini boshqaradi */ }
```

### O — Open/Closed Principle (Kengaytirishga ochiq, o'zgartirishga yopiq)
Yangi funksionallik qo'shish uchun mavjud kodni o'zgartirmasdan, kengaytirish orqali qo'shish kerak.

```kotlin
interface AdProvider {
    fun showAd()
}

class AdMobProvider : AdProvider { override fun showAd() { /* AdMob */ } }
class UnityAdsProvider : AdProvider { override fun showAd() { /* Unity Ads */ } }
// Yangi provider qo'shish mavjud kodga tegmaydi
```

### L — Liskov Substitution Principle
Subklass o'z superklassi o'rnida ishlatilganda dastur to'g'ri ishlashi kerak — subklass "va'dalarni" buzmasligi kerak.

```kotlin
// Yomon: Square Rectangle'ning kontraktini buzadi
open class Rectangle(open var width: Int, open var height: Int)
class Square(side: Int) : Rectangle(side, side) {
    override var width = side
        set(value) { field = value; height = value } // kutilmagan yon ta'sir
}
```

### I — Interface Segregation Principle
Katta, "hammasi bitta" interfeys o'rniga — kichik, aniq maqsadli interfeyslar.

```kotlin
// Yomon
interface Worker {
    fun code()
    fun design()
    fun testQA()
}

// Yaxshi
interface Coder { fun code() }
interface Designer { fun design() }
interface Tester { fun testQA() }
```

### D — Dependency Inversion Principle
Yuqori darajali modullar quyi darajali modullarga emas, **abstraksiyalarga** bog'liq bo'lishi kerak. (Clean Architecture'dagi Repository pattern shu tamoyilga asoslanadi.)

```kotlin
// Yomon: ViewModel to'g'ridan-to'g'ri Retrofit'ga bog'liq
class UserViewModel(private val api: RetrofitApiService)

// Yaxshi: ViewModel interfeysga bog'liq
interface UserRepository { suspend fun getUser(id: String): User }
class UserViewModel(private val repository: UserRepository)
class UserRepositoryImpl(private val api: RetrofitApiService) : UserRepository { /* ... */ }
```

---

## 4. DRY — Don't Repeat Yourself

Bir xil logika kodning bir necha joyida takrorlanmasin. Agar bir xil kodni 2-3 marta yozayotgan bo'lsangiz — uni funksiya, extension yoki base klassga chiqaring.

```kotlin
// Yomon: takrorlangan validatsiya
fun registerUser(email: String) {
    if (!email.contains("@")) throw IllegalArgumentException("Invalid email")
    // ...
}
fun updateEmail(email: String) {
    if (!email.contains("@")) throw IllegalArgumentException("Invalid email")
    // ...
}

// Yaxshi
fun String.isValidEmail(): Boolean = this.contains("@")

fun registerUser(email: String) {
    require(email.isValidEmail()) { "Invalid email" }
}
fun updateEmail(email: String) {
    require(email.isValidEmail()) { "Invalid email" }
}
```

**Ogohlantirish:** DRY'ni haddan tashqari qo'llash zararli bo'lishi mumkin (masalan, tasodifan o'xshab qolgan, lekin mantiqan bog'liq bo'lmagan ikkita narsani majburan bitta funksiyaga birlashtirish). Faqat **haqiqatan bir xil ma'no va sababga ega** kodni birlashtiring.

---

## 5. KISS — Keep It Simple, Stupid

Eng sodda yechim, agar u talabni qondirsa — eng yaxshi yechimdir.

- Kelajakda "kerak bo'lishi mumkin" degan narsalar uchun ortiqcha abstraksiya yaratmang (YAGNI — You Aren't Gonna Need It bilan birga ishlaydi)
- Aqlli, ammo tushunish qiyin bo'lgan bir qatorlik "hack"lardan qoching
- Murakkab design pattern kerak bo'lmasa, ishlatmang

```kotlin
// Ortiqcha murakkab
fun isEven(n: Int): Boolean = when {
    n == 0 -> true
    n < 0 -> isEven(-n)
    else -> isEven(n - 2)
}

// Sodda va tushunarli
fun isEven(n: Int): Boolean = n % 2 == 0
```

---

## 6. Tezkor tekshiruv ro'yxati (Code Review Checklist)

- [ ] Nomlar niyatni aniq ifodalaydimi?
- [ ] Har bir funksiya/klass bitta vazifaga ega (SRP)mi?
- [ ] Yangi funksionallik mavjud kodni o'zgartirmasdan qo'shildimi (OCP)?
- [ ] Interfeyslar kichik va maqsadga yo'naltirilganmi (ISP)?
- [ ] Bog'liqliklar abstraksiya orqali kiritilganmi (DIP, DI)?
- [ ] Takrorlangan logika bormi (DRY)?
- [ ] Yechim ortiqcha murakkab emasmi (KISS)?
- [ ] Xatolar to'g'ri boshqarilganmi (bo'sh catch yo'qmi)?
- [ ] Unit test yozish oson bo'lgan darajada kod ajratilganmi?

---

## 7. AI yordamchisi uchun qisqa prompt (nusxa oling)

```
Kod yozayotganda quyidagi qoidalarga qat'iy amal qil:
1. Clean Code: aniq nomlash, qisqa funksiyalar (bitta vazifa), early return,
   xatolarni yashirma.
2. SOLID: SRP, OCP, LSP, ISP, DIP tamoyillariga rioya qil — ayniqsa
   Repository/UseCase qatlamlarini interfeys orqali ajrat.
3. DRY: takrorlangan logikani umumiy funksiya/extension'ga chiqar,
   lekin faqat mantiqan bog'liq narsalarni birlashtir.
4. KISS: eng sodda ishlaydigan yechimni tanla, ortiqcha abstraksiya
   qo'shma (YAGNI).
Kotlin/Jetpack Compose va clean architecture konventsiyalariga mos yoz.
```

---

*Playnova loyihalari va EPAM EngX Clean Code kursi uchun tayyorlangan qo'llanma.*
